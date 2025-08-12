import os
import re
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd

sns.set_theme()

#data_folders = ["logs-0.5KB-1/", "logs-1KB-1/", "logs-2.5KB-1/", "logs-5KB-1/", "logs-10KB-1/",
#           "logs-20KB-1/", "logs-40KB-1/"]
#node_folders = ["../gossipsubdata_2nd/logs/", "../gossipsubdatarust/logs/", "../gossipsubdatago/logs/"]
#language = ["Nim", "Rust", "Go"]
data_folders = ["logs-10KB-1/"]
node_folders = ["../gossipsubdata_2nd/logs/", "../test/logs/"]
language = ["Before", "After"]

pattern = r'nds:\s[0-9]+'

final_df = pd.DataFrame()

for j, node_folder in enumerate(node_folders):
    folder_df = pd.DataFrame()
    for i, data_folder in enumerate(data_folders):
        file_df = pd.DataFrame()
        column_name = data_folder.split("-")[1][:-1]
        files = os.listdir(node_folder + data_folder)

        for log_file in files:
            values = []
            with open(node_folder + data_folder + log_file, 'r') as file:
                for line in file:
                    match = re.search(pattern, line)
                    if match:
                        value = int(match.group().split(":")[1].strip())
                        values.append(value)
            file_df = pd.concat([file_df, pd.Series(values)], ignore_index=True)

        file_df = file_df.rename({file_df.columns[0]: column_name}, axis=1)
        folder_df = pd.concat([folder_df, file_df], axis=1)

    folder_df["node"] = language[j]
    final_df = pd.concat([final_df, folder_df])

final_df = pd.melt(final_df, id_vars=["node"])
final_df = final_df.dropna()

box_plot = sns.boxplot(data=final_df, x="variable", y="value", hue="node")

plt.ylabel('Arrival Time (ms)')
plt.xlabel('Payload size (KB)')
plt.title('Times (N=300)')
plt.show()

box_plot.figure.savefig("test.png")

# remove outliers
final_df = final_df[final_df["value"] < 1000]

box_plot = sns.boxplot(data=final_df, x="variable", y="value", hue="node")

plt.ylabel('Arrival Time (ms)')
plt.xlabel('Payload size (KB)')
plt.title('Times (N=300)')
plt.show()

box_plot.figure.savefig("test_noo.png")
