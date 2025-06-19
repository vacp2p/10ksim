# from datetime import timedelta
# import logging
# import os
# import shutil
# from typing import List, Literal, Optional

# from pydantic import BaseModel, Field
# from yaml import YAMLObject

# from ruamel.yaml.comments import CommentedMap
# import yaml

# from deployment.builders import DeploymentBuilder
# from kube_utils import get_future_time, get_values_yamls, merge_helm_values, relative_paths, timedelta_until

# logger = logging.getLogger(__name__)

# def get_yaml_delay(
#     values_yaml: yaml.YAMLObject,
#     minutes_key: str,
#     hours_key: str,
# ):
#     if not values_yaml.get(minutes_key) and not values_yaml.get(hours_key):
#         return None
#     return timedelta_until(
#         hours=values_yaml.get(hours_key, "0"), minutes=values_yaml(minutes_key, "0")
#     )

# def set_delay( values_yaml : yaml.YAMLObject, hours_key: str, minutes_key:str, delay : str) -> timedelta:
#     hours, minutes = get_future_time(delay)
#     values_yaml[minutes_key] = minutes
#     values_yaml[hours_key] = hours

# class Nimlibp2pBuilder(BaseModel):
#     deployment_dir: str = Field(default=os.path.dirname(__file__))


#     def build(
#         self,
#         workdir: str,
#         cli_values: Optional[YAMLObject],
#         extra_values_names: Optional[List[str]] = None,
#         name: Optional[str] = None,
#     ) -> YAMLObject:
#         """

#         :param cli_values: Yaml object of values.yaml passed in main CLI.
#         :type cli_values: Optional[yaml.YAMLObject],

#         :param extra_values_names: The names of the extra values yamls to use from the ./values/ subdirectory. Eg. ["regression.yaml"]
#         :type extra_values_names: Optional[List[str]]

#         """
#         logger.debug(f"Building libnimp2p deployment file.")
#         if extra_values_names is None:
#             extra_values_names = []
#         if cli_values is None:
#             cli_values = CommentedMap()

#         service_dir = os.path.join(self.deployment_dir, "nodes")
#         delay = args.delay if args.delay is not None else default_delay
#         set_delay(cli_values, "hours", "minutes", delay)
#         # expected_start_time = datetime.now(timezone.utc) + delay
#         # return super().build(workdir, cli_values, service, )
