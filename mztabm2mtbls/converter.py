import json
import os
import subprocess
import sys
from typing import List

import click
from metabolights_utils import IsaTableFileReaderResult
from metabolights_utils.isatab import Reader, Writer
from metabolights_utils.models.isa.assay_file import AssayFile
from metabolights_utils.models.isa.assignment_file import AssignmentFile
from metabolights_utils.models.isa.investigation_file import (
    Assay, BaseSection, Factor, Investigation, InvestigationContacts,
    InvestigationPublications, OntologyAnnotation, OntologySourceReference,
    OntologySourceReferences, Person, Protocol, Publication, Study,
    StudyAssays, StudyContacts, StudyFactors, StudyProtocols,
    StudyPublications, ValueTypeAnnotation)
from metabolights_utils.models.isa.samples_file import SamplesFile
from metabolights_utils.models.metabolights.model import MetabolightsStudyModel

from mztabm2mtbls import utils
from mztabm2mtbls.mapper.base_mapper import BaseMapper
from mztabm2mtbls.mapper.metadata.metadata_assay import MetadataAssayMapper
from mztabm2mtbls.mapper.metadata.metadata_base import MetadataBaseMapper
from mztabm2mtbls.mapper.metadata.metadata_contact import MetadataContactMapper
from mztabm2mtbls.mapper.metadata.metadata_cv import MetadataCvMapper
from mztabm2mtbls.mapper.metadata.metadata_database import \
    MetadataDatabaseMapper
from mztabm2mtbls.mapper.metadata.metadata_publication import \
    MetadataPublicationMapper
from mztabm2mtbls.mapper.metadata.metadata_sample import MetadataSampleMapper
from mztabm2mtbls.mapper.metadata.metadata_sample_processing import \
    MetadataSampleProcessingMapper
from mztabm2mtbls.mapper.metadata.metadata_software import \
    MetadataSoftwareMapper
from mztabm2mtbls.mapper.summary.small_molecule_summary import \
    SmallMoleculeSummaryMapper
from mztabm2mtbls.mztab2 import MzTab

mappers: List[BaseMapper] = [
    MetadataBaseMapper(),
    MetadataContactMapper(),
    MetadataPublicationMapper(),
    MetadataCvMapper(),
    MetadataSampleMapper(),
    MetadataSampleProcessingMapper(),
    MetadataSoftwareMapper(),
    MetadataDatabaseMapper(),
    MetadataAssayMapper(),
    SmallMoleculeSummaryMapper(),
]


@click.command()
@click.option(
    "--input-file",
    default="test/data/singaporean-plasma-site1.mzTab",
    help="The mzTab-M file in .mzTab or .json format to convert.",
)
@click.option(
    "--output_dir", default="output", help="The directory to save the converted files."
)
@click.option(
    "--mtbls_accession_number",
    default="MTBLS1000000",
    help="The MetaboLights study accession number.",
)
@click.option("--container_engine", default="docker", help="Container run engine.")
@click.option(
    "--mztab2m_json_convertor_image",
    default="quay.io/biocontainers/jmztab-m:1.0.6--hdfd78af_1",
    help="Container image name to convert the mzTab-M file to mzTab-M json.",
)
@click.option(
    "--override_mztab2m_json_file",
    is_flag=False,
    default=False,
    help="If input file is mzTab-M file with extension .mzTab or .txt" 
        " and there is a mzTab-M json formatted version of the same file on same directory,"
        " overrides the current json file.",
)
def convert(
    input_file: str,
    output_dir: str,
    mtbls_accession_number: str,
    container_engine: str,
    mztab2m_json_convertor_image: str,
    override_mztab2m_json_file: str
):
    input_json_file = input_file
    # print disclaimer that we currently do not fully validate neither the mzTab-M file, nor the ISA-Tab files
    print(
        "Please note that the mzTab-M file is not fully validated by this tool.",
        "The ISA-Tab files are not validated either at the moment."
    )

    if input_file.startswith("test/data/singa"):
        print("Using default input file: test/data/singaporean-plasma-site1.mzTab")
        print("Please use the --input-file option to specify a custom input file.")

    _, extension = os.path.splitext(input_file)
    if extension.lower() != ".json":
        input_json_file = f"{input_file}.json"
        if not override_mztab2m_json_file and os.path.exists(input_json_file):
            print(f"{input_json_file} file exists, it will be used as an input.")
        else:
            abs_path = os.path.realpath(input_file)
            dirname = os.path.dirname(abs_path)
            filename = os.path.basename(abs_path)
            print(
                "Converting mzTab file to mzTab json format.",
                "Please check container management tool (docker, podman, etc.) is installed and runnig."
            )
            task = None
            try:
                task = subprocess.run(
                    [
                        "sh",
                        "-c",
                        f"{container_engine} run --rm -v {dirname}:/home/data:rw --workdir=/home/data {mztab2m_json_convertor_image}" 
                        f" jmztab-m -c /home/data/{filename} --toJson -o /home/data/{filename}_validation.txt",
                    ],
                    capture_output=True, text=True, check=True, timeout=120
                )
            except subprocess.TimeoutExpired as exc:
                print("The conversion of the mzTab file to mzTab json format timed out.")
                sys.exit(1)
            except subprocess.CalledProcessError as exc:
                print("The conversion of the mzTab file to mzTab json format failed.")
                print(exc.stderr)
                sys.exit(1)
            except Exception as exc:
                print("The conversion of the mzTab file to mzTab json format failed.")
                if task and task.stderr:
                    print(task.stderr)
                else:
                    print(str(exc))
                sys.exit(1)
            finally:
                if task and task.stdout:
                    print(task.stdout)
    
    with open(input_json_file) as f:
        mztab_json_data = json.load(f)
    utils.replace_null_string_with_none(mztab_json_data)
    mztab_model: MzTab = MzTab.model_validate(mztab_json_data)
    utils.modify_mztab_model(mztab_model)
    mtbls_model: MetabolightsStudyModel = utils.create_metabolights_study_model(
        study_id=mtbls_accession_number
    )

    for mapper in mappers:
        mapper.update(mztab_model, mtbls_model)
    study_metadata_output_path = os.path.join(output_dir, mtbls_accession_number)
    utils.save_metabolights_study_model(
        mtbls_model, output_dir=study_metadata_output_path
    )


if __name__ == "__main__":
    convert()
