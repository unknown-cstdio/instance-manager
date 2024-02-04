# Just for performing some analysis on the folders here..
from os import listdir
from os.path import isfile, join
import os

def get_all_files_in_dir(mypath):
    return [join(mypath, f) for f in listdir(mypath) if isfile(join(mypath, f))]

if __name__ == '__main__':
    all_directories = (next(os.walk('.'))[1])

    for directory in all_directories:
        # Create an empty txt file:
        with open(f"{directory}/cleaned-data.txt", "w") as f:
            
            # Get all files in directory:
            all_files = get_all_files_in_dir(directory)
            print(all_files)
        
            all_txt_files = [f for f in all_files if f.endswith(".txt")]
            # Remove the newly created file from the list:
            all_txt_files.remove(f"{directory}/cleaned-data.txt")
            
            # For each file in directory, find lines beginning with "Created", and write them to a new file:
            for file in all_txt_files:
                with open(file, "r") as resultsfile:
                    lines = resultsfile.readlines()
                    f.write("Starting new file: {}\n".format(file))
                    for line in lines:
                        if line.startswith("Created") or line.startswith("Total"):
                            f.write(line)
                    f.write("\n")
# Get all files in directory:

# For each file in directory, find lines beginning with "Created", and write them to a new file:
