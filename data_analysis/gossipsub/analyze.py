import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_theme()

# Read the CSV file
df = pd.read_csv('../../gossipsubdata/Tx.csv', parse_dates=['Time'], index_col='Time')

# Calculate the average for each column
df_avg = df.mean()

# Get the mean of df_avg
df_avg_mean = df_avg.median()
vertical_offset = df_avg.median() * 0.01  # offset from median for display

box_plot = sns.boxplot(data=df_avg).set_title('1K Gossipsub Rx')

# Plot the median value number in the boxplot
plt.text(0, df_avg_mean + vertical_offset, df_avg_mean, horizontalalignment='center',
         size='medium', weight='semibold')
# Set Left label
plt.ylabel('Bytes/s')
plt.tight_layout()

plt.show()

# Save figure
box_plot.figure.savefig("Tx.png")
