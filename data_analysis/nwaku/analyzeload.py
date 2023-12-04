import re
import matplotlib.pyplot as plt
import seaborn as sns


def extract_load_average(line):
    match = re.search(r':\s[0-9]*\.[0-9]+', line)
    if match:
        return float(match.group().split(":")[1].strip())
    else:
        return None

sns.set_theme()

files = ["logfilefsn", "logfilemetal01", "logfilemetal02"]
names = ["metal-01.he-eu-fsn1", "metal-01.he-eu-hel1", "metal-02.he-eu-hel1"]
waku_folders = ["load/50/", "load/100/", "load/150/", "load/300/", "load/600/", "load/1000/"]
gossipsub_folders = ["../gossipsubdata/load/50/", "../gossipsubdata/load/100/",
                     "../gossipsubdata/load/150/", "../gossipsubdata/load/300/",
                     "../gossipsubdata/load/600/", "../gossipsubdata/load/1000/"]


for i, file in enumerate(files):
    loads = []

    for folder in gossipsub_folders:
        current_load = []
        with open(folder+file, 'r') as f:
            for line in f:
                load_average = extract_load_average(line)
                if load_average is not None:
                    current_load.append(load_average)
        loads.append(current_load)

    for j, load in enumerate(loads):
        sns.lineplot(load[:180], label=gossipsub_folders[j].split("/")[-2], legend="full")

    plt.title(f'Gossipsub Loads ({names[i]})')
    plt.xlabel('Time (10s step)')
    plt.ylabel('uptime')
    plt.legend(title='Nodes', bbox_to_anchor=(1, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(f"load-gossipsub-{names[i]}.png")

    plt.show()


