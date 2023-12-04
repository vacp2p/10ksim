import re
import seaborn as sns
import matplotlib.pyplot as plt
import pandas as pd

sns.set_theme()

pattern = r'[0-9]*\.[0-9]+\sms'

files = ["publishers/publisher-container-50.log", "publishers/publisher-container-100.log",
         "publishers/publisher-container-150.log", "publishers/publisher-container-300.log",
         "publishers/publisher-container-600.log", "publishers/publisher-container-1000.log"]


final_df = pd.DataFrame()

for f in files:
    column_name = f.split("-")[2].split(".")[0]
    with open(f, 'r') as file:
        values = []
        for line in file:
            match = re.search(pattern, line)
            if match:
                value = float(match.group()[0:-3])
                values.append(value)
        final_df = pd.concat([final_df, pd.Series(values).rename(column_name)], axis=1)


box_plot = sns.boxplot(data=final_df).set_title('Waku REST response times')

plt.ylabel('Response time (ms)')
plt.xlabel('Nº nodes')
plt.show()

box_plot.figure.savefig("waku-times-unfiltered.png")
