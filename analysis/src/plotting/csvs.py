import os
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib import ticker

sns.set_theme()

language = ["Nim", "Rust", "Go"]

data_to_plot = ["Rx", "Tx", "Rp", "Tp", "Rpd", "Tpd"]
y_label = ["KBytes/s", "KBytes/s", "KPackets/s", "KPackets/s", "Packets/s", "Packets/s"]
scale = [True, True, False, False, False, False]

folders_grouped = [("../gossipsubdata_2nd/csv/rx/", "../gossipsubdatarust/csv/rx/", "../gossipsubdatago/csv/rx/"),
                   ("../gossipsubdata_2nd/csv/tx/", "../gossipsubdatarust/csv/tx/", "../gossipsubdatago/csv/tx/"),
                   ("../gossipsubdata_2nd/csv/rp/", "../gossipsubdatarust/csv/rp/", "../gossipsubdatago/csv/rp/"),
                   ("../gossipsubdata_2nd/csv/tp/", "../gossipsubdatarust/csv/tp/", "../gossipsubdatago/csv/tp/"),
                   ("../gossipsubdata_2nd/csv/rpd/", "../gossipsubdatarust/csv/rpd/", "../gossipsubdatago/csv/rpd/"),
                   ("../gossipsubdata_2nd/csv/tpd/", "../gossipsubdatarust/csv/tpd/", "../gossipsubdatago/csv/tpd/"), ]

# file_data = ["Rx-500B-1.csv", "Rx-1KB-1.csv", "Rx-2.5KB-1.csv", "Rx-10KB-1.csv", "Rx-20KB-1.csv"]
# file_data = ["Tx-500B-1.csv", "Tx-1KB-1.csv", "Tx-2.5KB-1.csv", "Tx-10KB-1.csv", "Tx-20KB-1.csv"]

fig, axs = plt.subplots(nrows=3, ncols=2, figsize=(14, 16), sharex=True, sharey='row')

for j, group in enumerate(folders_grouped):
    final_df = pd.DataFrame()
    for i, folder_path in enumerate(group):
        if not os.path.exists(folder_path): continue
        files = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]
        files = sorted(files, key=lambda x: float(x.split("-")[1].split("KB")[0]))
        folder_df = pd.DataFrame()

        for file in files:
            df = pd.read_csv(folder_path + file, parse_dates=['Time'], index_col='Time')

            column_name = file.split("-")[1]

            df_avg = df.mean()

            df_avg_mean = df_avg.median()
            vertical_offset = df_avg.median() * 0.05  # offset from median for display

            folder_df = pd.concat([folder_df, df_avg.rename(column_name)], axis=1)
        folder_df["node"] = language[i]
        final_df = pd.concat([final_df, folder_df])

    final_df = pd.melt(final_df, id_vars=["node"])

    box_plot = sns.boxplot(data=final_df, x="variable", y="value", hue="node", ax=axs[j // 2, j % 2])
    box_plot.set_title(f'{data_to_plot[j]} (N=300)')

    box_plot.set(xlabel='Payload size (KB)', ylabel=f"{y_label[j]}")
    box_plot.tick_params(labelbottom=True)
    # plt.ylabel(f"{y_label[j]}")
    # plt.xlabel('Payload size (KB)')

    # sns.move_legend(box_plot, "upper left", bbox_to_anchor=(1, 1))
    # plt.tight_layout()

    if scale[j]:
        # Create a custom formatter to divide x-axis ticks by 1000
        formatter = ticker.FuncFormatter(lambda x, pos: '{:.0f}'.format(x / 1000))
        # Apply the custom formatter to the x-axis ticks
        box_plot.yaxis.set_major_formatter(formatter)

plt.tight_layout()
plt.savefig(f"all.png")
plt.show()
# box_plot.figure.savefig(f"{data_to_plot[j]}-melted.png")
