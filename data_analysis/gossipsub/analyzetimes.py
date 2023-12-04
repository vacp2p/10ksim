import os
import re
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd

sns.set_theme()

folders = ["logs-50/", "logs-100/", "logs-150/", "logs-300/"]#, "logs-600/", "logs-1000/"]

pattern = r'nds:\s[0-9]+'


final_df = pd.DataFrame()

for i, f in enumerate(folders):
    folder_df = pd.DataFrame()
    column_name = f.split("-")[1][:-1]
    files = os.listdir("logs/" + f)
    for log_file in files:
        with open("logs/" + f + log_file, 'r') as file:
            values = []
            for line in file:
                match = re.search(pattern, line)
                if match:
                    value = int(match.group().split(":")[1].strip())
                    values.append(value)
            folder_df = pd.concat([folder_df, pd.Series(values)])
    folder_df = folder_df.rename({folder_df.columns[0]: column_name}, axis=1)

    final_df = pd.concat([final_df, folder_df])


box_plot = sns.boxplot(data=final_df).set_title('Gossipsub receive times')

plt.ylabel('Receive time (ms)')
plt.xlabel('Nº nodes')
plt.show()

box_plot.figure.savefig("gossipsub-times.png")
