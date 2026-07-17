// Flattens the nested {families: [{name, experiments: [...]}]} response into a
// flat list of experiments, each tagged with its family name. Shared between
// any page that needs to list/filter/sort experiments across all families.
export function flattenExperiments(familiesData) {
    const all = [];
    familiesData?.families?.forEach((family) => {
        family.experiments?.forEach((exp) => {
            all.push({ ...exp, family: family.name });
        });
    });
    return all;
}

export function sortByDateDesc(experiments) {
    return [...experiments].sort((a, b) => {
        if (!a.date) return 1;
        if (!b.date) return -1;
        return new Date(b.date) - new Date(a.date);
    });
}
