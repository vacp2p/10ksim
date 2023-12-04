import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_theme()

r_data_w = ["csv/Rx-50.csv", "csv/Rx-100.csv", "csv/Rx-150.csv", "csv/Rx-300.csv", "csv/Rx-600.csv", "csv/Rx-1000.csv"]
r_data_d = ["../gossipsubdata/csv/Rx-50.csv", "../gossipsubdata/csv/Rx-100.csv", "../gossipsubdata/csv/Rx-150.csv",
            "../gossipsubdata/csv/Rx-300.csv", "../gossipsubdata/csv/Rx-600.csv", "../gossipsubdata/csv/Rx-1000.csv"]
t_data = ["csv/Tx-50.csv", "csv/Tx-100.csv", "csv/Tx-150.csv", "csv/Tx-300.csv", "csv/Tx-600.csv", "csv/Tx-1000.csv"]

final_df = pd.DataFrame()

for data in r_data_w:
    column_name = data.split("-")[1].split(".")[0]

    df = pd.read_csv(data, parse_dates=['Time'], index_col='Time')

    df_avg = df.mean()

    df_avg_mean = df_avg.median()
    vertical_offset = df_avg.median() * 0.05  # offset from median for display

    final_df = pd.concat([final_df, df_avg.rename(column_name)], axis=1)


box_plot = sns.boxplot(data=final_df).set_title('nWaku Rx')

# # Plot the median value number in the boxplot
# plt.text(0, df_avg_mean + vertical_offset, df_avg_mean, horizontalalignment='center',
#          size='medium', weight='semibold')
# Set Left label
plt.ylabel('Bytes/s')
plt.xlabel('Nº nodes')
plt.tight_layout()

plt.show()
box_plot.figure.savefig("Rx-nwaku.png")
