import os
import re
pattern = r'[0-9]+\s[A-Za-z]+:\s[0-9]+'

folder_dir = "../gossipsubdata_2nd/logs/logs-20KB-1/"


def parse_file(data, folder):
    log_files = os.listdir(folder)
    for log_file in log_files:
        with open(folder + log_file, 'r') as file:
            for line in file:
                match = re.search(pattern, line)
                if match:
                    value = int(match.group().split(" ")[0])
                    if value not in data:
                        data[value] = [[log_file], 1]
                    else:
                        data[value][0].append(log_file)
                        data[value][1] += 1


all_data = {}
parse_file(all_data, folder_dir)

for key, value in sorted(all_data.items()):
    print(f"{key}: {value[1]}")

# Wednesday, 3 January 2024 13:40:03.052
# Wednesday, 3 January 2024 13:55:26.148

# Tuesday, 2 January 2024 14:16:03.825
# Tuesday, 2 January 2024 14:31:27.839