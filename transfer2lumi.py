#!/usr/bin/env python3

#
# Example on how to transfer data from atos to lumi.
# Data will be temporary located under hpc-login:$SCRATCH/case/run/...
#
# See https://github.com/DEODE-NWP/WP53/wiki/Transfer-your-case-to-lumi for setup guidance.
#
#
# Ulf Andrae, SMHI, 2023
#

import os
import sys
from argparse import ArgumentParser
from datetime import datetime, timedelta

import yaml

from cases import Cases, expand_dates, expand_times, hub

REQUIRED = ("selection", "remote")
GROUPS = {
    "dates": ("sdate", "edate", "step"),
    "leadtimes": ("stime", "etime", "leadtime_step"),
}


def check_config(config):

    for key, val in config.items():

        missing = [x for x in REQUIRED if x not in val]
        if len(missing) > 0:
            print(f"Missing required items in {key}:", missing)
            sys.exit()
        for group, items in GROUPS.items():
            explicit = group in val
            found = [x for x in items if x in val]
            if explicit and len(found) > 0:
                print(f"Specify either {group} or {items} for {key}")
                sys.exit()
            elif not explicit and len(found) < 3 and len(found) > 0:
                print(f"Specify all of {items} or {group} for {key}")
                sys.exit()

            if not explicit and len(found) == 3:

                if group == "dates":
                    sdate = datetime.strptime(val["sdate"], "%Y-%m-%d %H")
                    edate = datetime.strptime(val["edate"], "%Y-%m-%d %H")
                    step = step2td(val["step"])
                    config[key][group] = expand_dates(sdate, edate, step)

                if group == "leadtimes":
                    for y in items:
                        config[key][y] = step2td(val[y])
                    config[key][group] = expand_times(
                        config[key]["stime"],
                        config[key]["etime"],
                        config[key]["leadtime_step"],
                    )

            elif not explicit and len(found) == 0:
                config[key][group] = []

    return config


#########################################


def step2td(step):
    if isinstance(step, int):
        return timedelta(seconds=step)
    else:
        (hour, minute, second) = [int(x) for x in step.split(":")]
        return timedelta(
            days=int(hour / 24), hours=(hour % 24), seconds=60 * minute + second
        )


#########################################


def transfer(cfg):

    print("Config:", cfg["selection"])

    # Load the metadata
    example = Cases(selection=cfg["selection"], printlev=0, host="atos")

    for case in example.names:
        for exp in example.cases.names:
            if cfg["remote"] not in example.meta[case][exp]:
                print(f"  {cfg['remote']} not defined for {case}/{exp}")
                continue

            outpath_template = example.meta[case][exp][cfg["remote"]]["path_template"]
            print(f" transfer data to:", outpath_template)

            scratch_template = os.path.join(
                os.environ["SCRATCH"], case, exp, "%Y/%m/%d/%H/"
            )


            i=0
            file_template_used = None
            if "file_template" in cfg:
              file_template_used = cfg["file_template"]
              try:
                i = example.cases.runs.file_templates.index(cfg["file_template"])
              except ValueError:
                  print("No match for:", cfg["file_template"])
                  sys.exit()
            file_template = example.cases.runs.file_templates[i]

            x = example.cases.runs.data

            if file_template not in x:
                print(" no data available for:", file_template)
                continue

            for date in x[file_template].keys():

                if len(cfg["dates"]) > 0:
                    cdate = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
                    if cdate not in cfg["dates"]:
                        continue

                print(" fetch:", date)

                # Parse the paths and expand the dates
                remote_outpath = hub(outpath_template, date)
                scratch_outpath = hub(scratch_template, date)

                # Get a list of files
                files = example.reconstruct(dtg=date, leadtime=cfg["leadtimes"], file_template=file_template_used)

                # Do the actual copy from ecf to scratch and rsync to lumi,
                # and clean the intermediate files
                example.transfer(
                    files,
                    scratch_outpath,
                    {"host": cfg["remote"], "outpath": remote_outpath},
                )


#########################################################################
def main(argv):

    parser = ArgumentParser(
        description="DE_330 Case Meta DataBase data transfer at your service"
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        required=True,
        default=None,
        help="Config file for data transfers",
    )

    args = parser.parse_args()
    config = yaml.safe_load(open(args.config))
    config = check_config(config)

    for trans, vals in config.items():
        selection = vals["selection"]
        show = Cases(selection=selection, printlev=0, host="atos")
        for case in show.names:
            for run in show.cases.names:
                vals["selection"] = {case: run}
                transfer(vals)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

