Each subfolder (nimlibp2p2, waku, etc) contains all the resources to
set up and run experiments for that type of deployment.

See the README.md under each subfolder for more details.

When creating a new deployment type:

- Use the file suffix `.values.yaml` for helper values yamls.
  Within each deployment, for each `*.values.yaml` file under the project dir,
  `--values <file.values.yaml>` will be added to the `helm template` command.
- `.values.yaml` files should be under `./templates`.
  That is where `get_values_yamls` looks for values yamls.
- Common values should be in `<project_dir>/values.yaml`.
  This is in-line with `helm` conventions[¹](https://helm.sh/docs/chart_template_guide/values_files/).
- Helper templates (`.tpl` files) should have a leading underscore (eg. `_metrics.tpl`).
  Otherwise, the file will be treated as a deployment, and the output file from
  `helm template` will have an extra yaml document from the `.tpl` file.

