import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_theme()

folders = ["../gossipsubdata/packet/", "packet/"]
node = ["Gossipsub", "nWaku"]

r_data = ["RPD-150.csv", "RPD-300.csv", "RPD-600.csv", "RPD-1000.csv"]
t_data = ["TPD-150.csv", "TPD-300.csv", "TPD-600.csv", "TPD-1000.csv"]

final_df = pd.DataFrame()

for i, folder in enumerate(folders):
    folder_df = pd.DataFrame()
    for data in t_data:
        column_name = data.split("-")[1].split(".")[0]

        try:
            df = pd.read_csv(folder+data, parse_dates=['Time'], index_col='Time')
        except FileNotFoundError:
            print(f"{folder+data} not found")
            continue

        df_avg = df.mean()

        df_avg_mean = df_avg.median()
        vertical_offset = df_avg.median() * 0.05  # offset from median for display

        folder_df = pd.concat([folder_df, df_avg.rename(column_name)], axis=1)
    folder_df["node"] = node[i]
    final_df = pd.concat([final_df, folder_df])

final_df = pd.melt(final_df, id_vars=["node"])

box_plot = sns.boxplot(data=final_df, x="variable", y="value", hue="node")

# # Plot the median value number in the boxplot
# plt.text(0, df_avg_mean + vertical_offset, df_avg_mean, horizontalalignment='center',
#          size='medium', weight='semibold')
# Set Left label
plt.ylabel('TPD/s')
plt.xlabel('Nº nodes')
plt.title("TPD")
plt.tight_layout()

plt.show()
box_plot.figure.savefig("RPD-melted.png")
