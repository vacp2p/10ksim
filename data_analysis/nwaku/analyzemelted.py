import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_theme()

folders = ["../gossipsubdata/csv/", "csv/"]
node = ["Gossipsub", "nWaku"]

r_data = ["Rx-50.csv", "Rx-100.csv", "Rx-150.csv", "Rx-300.csv", "Rx-600.csv", "Rx-1000.csv"]
t_data = ["Tx-50.csv", "Tx-100.csv", "Tx-150.csv", "Tx-300.csv", "Tx-600.csv", "Tx-1000.csv"]

final_df = pd.DataFrame()
for i, folder in enumerate(folders):
    folder_df = pd.DataFrame()
    for data in r_data:
        column_name = data.split("-")[1].split(".")[0]

        df = pd.read_csv(folder+data, parse_dates=['Time'], index_col='Time')

        df_avg = df.mean()

        df_avg_mean = df_avg.median()
        vertical_offset = df_avg.median() * 0.05  # offset from median for display

        folder_df = pd.concat([folder_df, df_avg.rename(column_name)], axis=1)
    folder_df["node"] = node[i]
    final_df = pd.concat([final_df, folder_df])

final_df = pd.melt(final_df, id_vars=["node"])

box_plot = sns.boxplot(data=final_df, x="variable", y="value", hue="node")
box_plot.set_title('Rx')
# # Plot the median value number in the boxplot
# plt.text(0, df_avg_mean + vertical_offset, df_avg_mean, horizontalalignment='center',
#          size='medium', weight='semibold')
# Set Left label
plt.ylabel('Bytes/s')
plt.xlabel('Nº nodes')

sns.move_legend(box_plot, "upper left", bbox_to_anchor=(1, 1))
plt.tight_layout()
plt.show()
box_plot.figure.savefig("Rx-melted.png")
