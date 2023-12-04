import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_theme()

folder = "../gossipsubdata/packet/"
r_data = ["RPD-300.csv", "RPD-600.csv", "RPD-1000.csv"]
t_data = ["TPD-300.csv", "TPD-600.csv", "TPD-1000.csv"]

final_df = pd.DataFrame()

for data in t_data:
    column_name = data.split("-")[1].split(".")[0]

    df = pd.read_csv(folder+data, parse_dates=['Time'], index_col='Time')

    df_avg = df.mean()

    df_avg_mean = df_avg.median()
    vertical_offset = df_avg.median() * 0.05  # offset from median for display

    final_df = pd.concat([final_df, df_avg.rename(column_name)], axis=1)


box_plot = sns.boxplot(data=final_df).set_title('Gossipsub TPD')

# # Plot the median value number in the boxplot
# plt.text(0, df_avg_mean + vertical_offset, df_avg_mean, horizontalalignment='center',
#          size='medium', weight='semibold')
# Set Left label
plt.ylabel('TPD/s')
plt.xlabel('Nº nodes')
plt.tight_layout()

plt.show()
box_plot.figure.savefig("gossipsub-TPD.png")
