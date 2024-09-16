import os
import logging
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def clean_yaml_file(file_path):
    """
    Preprocess the YAML file to remove Python-specific tags.
    """
    cleaned_lines = []
    try:
        with open(file_path, 'r') as file:
            for line in file:
                # Remove or skip lines with Python-specific tags
                if '!!python/object/apply:collections.OrderedDict' not in line:
                    cleaned_lines.append(line)
                else:
                    logging.warning(f"Skipping Python-specific line in {file_path}: {line.strip()}")

        # Write cleaned content back to a temporary file
        temp_file_path = f"{file_path}.tmp"
        with open(temp_file_path, 'w') as temp_file:
            temp_file.writelines(cleaned_lines)
        logging.info(f"Cleaned Python-specific tags from {file_path}.")

        return temp_file_path

    except Exception as e:
        logging.error(f"Error cleaning file {file_path}: {e}")
        return None

def append_yaml_content(source_file, target_file):
    """
    Append the content of source_file to target_file as YAML.
    """
    try:
        # Check if source file exists and read YAML content
        if not os.path.isfile(source_file):
            logging.error(f"The source file {source_file} does not exist.")
            return
        
        with open(source_file, 'r') as src:
            source_content = yaml.safe_load(src) or []
        logging.info(f"Read YAML content from {source_file} successfully.")

    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML in {source_file}: {e}")
        return
    except PermissionError:
        logging.error(f"Permission denied while reading {source_file}. Please check your file permissions.")
        return
    except Exception as e:
        logging.error(f"An error occurred while reading {source_file}: {e}")
        return

    # Preprocess the target file to clean Python-specific tags
    cleaned_target_file = clean_yaml_file(target_file)
    if not cleaned_target_file:
        logging.error("Failed to clean target file of Python-specific tags.")
        return

    try:
        # Load existing content from the cleaned target file
        existing_content = {}
        if os.path.isfile(cleaned_target_file):
            with open(cleaned_target_file, 'r') as tgt:
                existing_content = yaml.safe_load(tgt) or {}
            logging.info(f"Loaded existing YAML content from {cleaned_target_file}.")

        # Ensure the YAML structure is correct
        if 'roles' not in existing_content:
            existing_content['roles'] = []
        if not isinstance(existing_content['roles'], list):
            logging.error(f"'roles' key in {target_file} is not a list. Aborting operation.")
            return
        
        # Append source content to existing content's 'roles' key
        if isinstance(source_content, list):
            existing_content['roles'].extend(source_content)
        else:
            logging.error("Source content is not a list. Aborting operation.")
            return

        # Write combined content back to the target file
        with open(target_file, 'w') as tgt:
            yaml.safe_dump(existing_content, tgt, default_flow_style=False, sort_keys=False)
        logging.info(f"Appended content from {source_file} to {target_file} successfully.")

    except yaml.YAMLError as e:
        logging.error(f"Error parsing YAML in {target_file}: {e}")
    except PermissionError:
        logging.error(f"Permission denied while writing to {target_file}. Please check your file permissions.")
    except Exception as e:
        logging.error(f"An error occurred while writing to {target_file}: {e}")

if __name__ == "__main__":
    source_file = input("Enter the path of the source YAML file to read from: ")
    target_file = input("Enter the path of the target YAML file to append to: ")

    append_yaml_content(source_file, target_file)
