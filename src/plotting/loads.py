import os

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_theme()

language = ["Nim", "Rust", "Go"]
server = ["metal-01.he-eu-hel1.vacdst.misc", "metal-01.he-eu-fsn1.vacdst.misc"]

folders_grouped = [("../gossipsubdata_2nd/load/109/", "../gossipsubdatarust/load/109/", "../gossipsubdatago/load/109/"),
                   ("../gossipsubdata_2nd/load/198/", "../gossipsubdatarust/load/198/", "../gossipsubdatago/load/198/")]


for j, group in enumerate(folders_grouped):
    for i, folder_path in enumerate(group):
        if not os.path.exists(folder_path): continue
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        files = sorted(files, key=lambda x: float(x.split("-")[1].split("KB")[0]))

        for file in files:
            df = pd.read_csv(folder_path + file)

            # get column as list
            df = df['1m load average'].tolist()

            sns.lineplot(df, label=file.split("-")[1], legend="full")

        plt.xlabel('Time (1min step)')
        plt.ylabel('uptime')
        plt.title(f'Nim Loads ({server[j]})')
        plt.legend(title='Nodes', bbox_to_anchor=(1, 1), loc='upper left')
        plt.tight_layout()

        plt.savefig(f"{language[i]}-{server[j]}.png")
        plt.show()
