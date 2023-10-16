#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
import shutil
from datetime import datetime

import yaml


class Cases:
    def __init__(self, names=None, path=None, printlev=None, host=None, selection=None):

        self.path = path if path is not None else "cases"
        self.printlev = printlev if printlev is not None else 1
        self.host = host if host is not None else self.get_hostname()
        self.selection = selection if selection is not None else {}

        if isinstance(self.selection, str):
            self.selection = [self.selection]
        if isinstance(self.selection, list):
            self.selection = {k: [] for k in self.selection}

        if names is None:
            if self.selection is not None:
                self.names = list(self.selection.keys())
            else:
                self.names = []
        elif isinstance(names, str):
            self.names = [names]
        else:
            self.names = names

        self.cases, self.names, self.meta = self.load_cases()

        self.domains = {}
        for k, v in self.meta.items():
            self.domains[k] = {}
            for x, y in v.items():
                self.domains[k][x] = y["domain"]

        if len(self.names) == 0:
            print("No cases found")
            print(
                "Available cases:",
                [x.split("/")[0] for x in find_files(self.path, "meta.yaml")],
            )
            sys.exit()

    #########################################################################
    def get_hostname(self):

        import socket

        host = socket.gethostname()
        if re.search(r"^a(a|b|c|d)", host):
            return "atos"

        return None

    #########################################################################
    def scan(self):
        if isinstance(self.cases, dict):
            for case in self.cases:
                self.cases[case].scan()
        else:
            self.cases.scan()

    #########################################################################
    def load_cases(self):
        def intersection(lst1, lst2):
            lst3 = [value for value in lst1 if value in lst2]
            lst4 = [value for value in lst1 if value not in lst3]
            return lst3, lst4

        meta_file = "meta.yaml"
        case_list = [x.split("/")[0] for x in find_files(self.path, meta_file)]
        if self.names is not None:
            if len(self.names) > 0:
                case_list, missing = intersection(self.names, case_list)
                if len(missing) > 0:
                    print("\nCould not find cases:", missing, "\n")

        if len(case_list) == 0:
            return {}, [], {}

        res = {}
        mm = {}
        for x in case_list:
            p = "{}/{}/{}".format(self.path, x, meta_file)
            meta = yaml.safe_load(open(p))
            if x in self.selection:
                y = self.selection[x]
                if isinstance(y, str):
                    y = [y]
                if len(y) > 0:
                    exp_list, missing = intersection(y, meta.keys())
                    if len(missing) > 0:
                        print("\nCould not find exp:", missing, "\n")
                    meta = {k: v for k, v in meta.items() if k in exp_list}

            mm[x] = meta
            res[x] = Case(self.host, self.path, self.printlev, meta, x)

        if self.printlev > 0:
            print("Loaded:", case_list)
        if len(res) > 1:
            return res, case_list, mm
        else:
            return res[x], case_list, mm

    #########################################################################
    def show(self):

        for case, body in self.cases.items():
            print("\nCase:", case)
            print("   ", body)

    #########################################################################
    def print(self, printlev=None):

        if printlev is not None:
            self.printlev = printlev

        if self.printlev < 0:
            print("Cases:", self.names)
            return

        if isinstance(self.cases, dict):
            for name, case in self.cases.items():
                print("\nCase:", name)
                case.print(self.printlev)
        else:
            self.cases.print(self.printlev)

    #########################################################################
    def toc(self, printlev=None):

        if printlev is not None:
            self.printlev = printlev

        if isinstance(self.cases, dict):
            for name, case in self.cases.items():
                print("\nCase:", name)
                case.toc(self.printlev)
        else:
            self.cases.toc(self.printlev)

    #########################################################################
    def reconstruct(self, dtg=None, leadtime=None, file_template=None):

        res = []
        if isinstance(self.cases, dict):
            for name, case in self.cases.items():
                res.extend(case.reconstruct(dtg, leadtime, file_template))
        else:
            res.extend(self.cases.reconstruct(dtg, leadtime, file_template))

        return res

    #########################################################################
    def get(self, files=[], outpath="."):

        clean = True
        for f in files:
            if re.match("^ec", f):
                ecfs_copy(f, outpath, self.printlev)
            else:
                try:
                  os.symlink(f, os.path.join(outpath, os.path.basename(f)))
                except FileExistsError:
                  clean = False

        return clean

    #########################################################################
    def clean(self, files=[], outpath="."):

        for fname in files:
            f = os.path.join(outpath, os.path.basename(fname))
            os.remove(f)
            print("  remove:", f)

    #########################################################################
    def check_remote(self, files=[], remote=None):

        bare_files = [os.path.basename(x) for x in files]
        listcmd = ["ssh", remote["host"], "ls", "-1", remote["outpath"]]
        missing_files = []
        cmd = subprocess.Popen(listcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        cmd_out, cmd_err = cmd.communicate()
        if cmd_out is not None:
            for line in cmd_out.splitlines():
                fname = line.decode("utf-8")
                try:
                    i = bare_files.index(fname)
                    bare_files.pop(i)
                except ValueError:
                    pass

        return bare_files

    #########################################################################
    def transfer(self, files=[], outpath=".", remote=None):

        os.makedirs(outpath, exist_ok=True)
        missing_files = self.check_remote(files, remote)

        if len(missing_files) > 0:
            nfiles = len(missing_files)
            print(f"  Transfer {nfiles} files this date")
            clean = self.get(files, outpath)
            cmd = 'ssh {} "mkdir -p {}"'.format(remote["host"], remote["outpath"])
            print(cmd)
            os.system(cmd)
            rhost = remote["host"]
            rpath = remote["outpath"]
            cmd = f"rsync -vaux --copy-unsafe-links {outpath}/ {rhost}:{rpath}/"
            print(cmd)
            os.system(cmd)
            if clean:
              self.clean(files, outpath)
        else:
            nfiles = len(files)
            print(f"  all {nfiles} files already in place for this date")
            if self.printlev > 0:
                print(files)


#########################################################################
class Case:
    def __init__(self, host, path, printlev, props, case):

        self.host, self.path, self.printlev = host, path, printlev
        self.case = case
        self.printlev = printlev

        self.data = self.load()
        self.runs = {}
        if len(props) > 1:
            for exp, val in props.items():
                if host in val:
                    try:
                        if exp not in self.data[host]:
                            self.data[host][exp] = {}
                    except KeyError:
                         self.data[host]={}
                         self.data[host][exp] = {}
                    self.runs[exp] = Exp(
                        path, case, exp, host, printlev, val, self.data[host][exp]
                    )
        else:
            for exp, val in props.items():
                if host in val:
                    if exp not in self.data[host]:
                        self.data[host][exp] = {}
                    self.runs = Exp(
                        path, case, exp, host, printlev, val, self.data[host][exp]
                    )
        self.names = [x for x in props]

    ##############################################################################
    def print(self, printlev=None):
        if printlev is not None:
            self.printlev = printlev

        if self.printlev == 0:
            print(" Runs:", self.names)
            return

        if isinstance(self.runs, dict):
            for run, exp in self.runs.items():
                exp.print(self.printlev)
        else:
            self.runs.print(self.printlev)

    ##############################################################################
    def toc(self, printlev=None):
        if printlev is not None:
            self.printlev = printlev

        if isinstance(self.runs, dict):
            for run, exp in self.runs.items():
                exp.toc(self.printlev)
        else:
            self.runs.toc(self.printlev)

    ##############################################################################
    def load(self):
        filename = f"{self.path}/{self.case}/data.json"
        if os.path.isfile(filename):
            with open(filename, "r") as infile:
                data = json.load(infile)
                infile.close()
        else:
            data = {}
            data[self.host] = {}
        return data

    def scan(self):
        findings = {}
        if isinstance(self.runs, dict):
            for name, exp in self.runs.items():
                result, signal = exp.scan()
                if signal:
                    self.data[self.host][name] = result
                else:
                    print("  no data found for", name)
        else:
            result, signal = self.runs.scan()
            if signal:
                self.data[self.host][self.names[0]] = result
            else:
                print("  no data found for", self.names)

        # Print a summary
        if self.printlev > 0:
            print(" Scan result:")
            self.print()

        self.dump()

    #########################################################################
    def dump(self):
        filename = f"{self.path}/{self.case}/data.json"
        with open(filename, "w") as outfile:
            print("  write to:", filename)
            json.dump(self.data, outfile, indent=1)
            outfile.close()

    #########################################################################
    def reconstruct(self, dtg=None, leadtime=None, file_template=None):
        res = []
        if isinstance(self.runs, dict):
            for run, exp in self.runs.items():
                res.extend(exp.reconstruct(dtg, leadtime, file_template))
        else:
            res.extend(self.runs.reconstruct(dtg, leadtime, file_template))
        return res


#########################################################################
class Exp:
    def __init__(self, path, case, name, host, printlev, val, data):

        self.path = path
        self.case = case
        self.name = name
        self.host = host
        self.printlev = printlev
        self.file_templates = val["file_templates"]
        self.path_template = val[host]["path_template"]
        self.domain = val["domain"]
        self.data = data

    #########################################################################
    def check_template(self, x):

        known_keys = {
            "%Y": 4,  # Year
            "%m": 2,  # Month
            "%d": 2,  # Day
            "%H": 2,  # Hour
            "%M": 2,  # Minute
            "*": 0,  # Wildcard
            "%LM": 2,  # Leadtime in minutes
            "%LLLL": 4,  # Leadtime in hours
            "%LLL": 3,  # Leadtime in hours
            "%LL": 2,  # Leadtime in hours
        }

        mapped_keys = {}
        replace_keys = {}
        y = x
        for k, v in known_keys.items():
            kk = k
            if "%" in k:
                s = f"(\\d{{{v}}})"
            if "*" in k:
                s = f"(.*)"
                kk = "\*"
            if "+" in k:
                s = f"\+"

            mm = [m.start() for m in re.finditer(kk, x)]
            y = y.replace(k, s)
            if len(mm) > 0:
                mapped_keys[k] = mm[0]
                replace_keys[k] = s
                if k in ["%LLLL", "%LLL", "%LL"]:
                    break

        mk = dict(sorted(mapped_keys.items(), key=lambda item: item[1]))

        y = y.replace("+", "\+")

        return y, mk, replace_keys

    #########################################################################
    def reconstruct(self, dtg=None, leadtime=None, file_template=None):
        def matching(files, src):
            res = []
            for f in files:
                for x in src:
                    if f == x:
                        res.append(f)
                    else:
                        m = re.fullmatch(f, x)
                        if m is not None:
                            res.append(m.group(0))

            return res

        def sub(p, dtgs, leadtime):

            dtg = datetime.strptime(dtgs, "%Y-%m-%d %H:%M:%S")
            lh, lm = leadtime2hm(leadtime)
            path = p

            re_map = {
                "%Y": "{:04d}".format(dtg.year),
                "%m": "{:02d}".format(dtg.month),
                "%d": "{:02d}".format(dtg.day),
                "%H": "{:02d}".format(dtg.hour),
                "%M": "{:02d}".format(dtg.minute),
                "%S": "{:02d}".format(dtg.second),
                "%LLLL": "{:04d}".format(lh),
                "%LLL": "{:03d}".format(lh),
                "%LL": "{:02d}".format(lh),
                "%LM": "{:02d}".format(int(lm)),
            }
            for k, v in re_map.items():
                path = path.replace(k, str(v))

            return path

        if file_template is None:
            files = self.file_templates
        else:
            files = [file_template]

        result = []
        for file in matching(files, self.data.keys()):
            if dtg is None or dtg == []:
                dtgs = list(self.data[file].keys())
            else:
                if isinstance(dtg, str):
                    dtgs = [dtg]
                else:
                    dtgs = dtg

            for ddd in dtgs:
                if ddd in self.data[file]:
                    if leadtime is None or leadtime == []:
                        leadtimes = self.data[file][ddd]
                    else:
                        if isinstance(leadtime, list):
                            leadtimes = [x for x in leadtime]
                        else:
                            leadtimes = [leadtime]

                    result.extend(
                        [
                            sub(f"{self.path_template}/{file}", ddd, l)
                            for l in leadtimes
                            if l in self.data[file][ddd]
                        ]
                    )

        return result

    #########################################################################
    def print(self, printlev=None):
        if printlev is not None:
            self.printlev = printlev
        print("\n ", self.name)
        print("   File templates:", self.file_templates)
        print("   Path template :", self.path_template)
        print("   Domain:", self.domain)
        for fname in self.file_templates:
            if fname in self.data:
                content = self.data[fname]
                dates = [d for d in sorted(content)]
                print("   File:", fname)
                if self.printlev < 2:
                    print("    Dates:", dates[0], "-", dates[-1])
                    if content[dates[0]][0] is None:
                        print("    No leadtime information available")
                    else:
                        maxlist = []
                        minlist = []
                        for date, leadtimes in sorted(content.items()):
                            maxlist.append(max(leadtimes))
                            minlist.append(min(leadtimes))
                        lhs, lms = leadtime2hm(min(minlist))
                        lhe, lme = leadtime2hm(max(maxlist))
                        print(
                            "    Leadtimes:{:02d}h{:02d}m - {:02d}h{:02d}m".format(
                                lhs, lms, lhe, lme
                            )
                        )
                elif self.printlev < 3:
                    if content[dates[0]][0] is not None:
                        for date, leadtimes in sorted(content.items()):
                            lhs, lms = leadtime2hm(leadtimes[0])
                            lhe, lme = leadtime2hm(leadtimes[-1])
                            print(
                                "    {} : {:02d}h{:02d}m - {:02d}h{:02d}m".format(
                                    date, lhs, lms, lhe, lme
                                )
                            )
                    else:
                        for date in sorted(dates):
                            print("    ", date)
                elif self.printlev > 2:
                    if content[dates[0]][0] is not None:
                        for date, leadtimes in sorted(content.items()):
                            print("   ", date, ":")
                            x = leadtimes[0]
                            fh, lm = leadtime2hm(x)
                            txt = "       {:02d}h : {:02d}".format(fh, lm)
                            for x in leadtimes[1:]:
                                lh, lm = leadtime2hm(x)
                                if lh == fh:
                                    txt += ",{:02d}".format(lm)
                                else:
                                    print(txt + "m")
                                    txt = "       {:02d}h : {:02d}".format(lh, lm)
                                    fh = lh
                            print(txt + "m")

                if self.printlev > 1:

                    if content[dates[0]][0] is None:
                        example = self.reconstruct(dates[0], file_template=fname)
                    else:
                        example = self.reconstruct(
                            dates[0], content[dates[0]][-1], fname
                        )
                    print("    Example:", example)
                    if re.match("^ec", example[0]):
                        if self.printlev > 2:
                            print("Checking", example[0])
                        listcmd = ["els", "-l", example[0]]
                        cmd = subprocess.Popen(
                            listcmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                        )
                        cmd_out, cmd_err = cmd.communicate()
                        if cmd_out is not None:
                            for line in cmd_out.splitlines():
                                tmp = line.decode("utf-8")
                                print(tmp)
                                if "msdeode" not in tmp:
                                    print(
                                        "ERROR:Wrong group for",
                                        self.case,
                                        ":",
                                        self.name,
                                        tmp,
                                    )

                        if cmd_err is not None:
                            for line in cmd_err.splitlines():
                                tmp = line.decode("utf-8")
                                print(
                                    "ERROR:Problem listing",
                                    self.case,
                                    ":",
                                    self.name,
                                    tmp,
                                )

    #########################################################################
    def build_toc(self, file_template, file_to_scan):

        isgrib, issfx, grib_version = self.check_file_type(file_template)
        json_filename = f"{self.path}/{self.case}/{self.name}_{file_template}.json"

        if os.path.isfile(json_filename) and self.printlev > 0:
            print(f" found {json_filename}")
        elif isgrib and not os.path.isfile(json_filename):
            print(f" create {json_filename}")
            if issfx and grib_version == 1:
                parameters = "indicatorOfParameter,level,typeOfLevel,timeRangeIndicator"
            elif grib_version == 1:
                parameters = "indicatorOfParameter,level,typeOfLevel,timeRangeIndicator,shortName"
            elif grib_version == 2:
                parameters = "discipline,parameterCategory,parameterNumber,level,typeOfLevel,stepType,shortName"

            if self.printlev > 0:
                print(" scanning", file_to_scan)

            if re.match("^ec", file_to_scan):
                outfile = f"{os.environ['SCRATCH']}/{os.path.basename(file_to_scan)}"
                found_file = os.path.isfile(outfile)
                if not found_file:
                    found_file = ecfs_copy(file_to_scan, outfile, self.printlev)
            else:
                outfile = file_to_scan
                found_file = True

            if found_file:
                json_filename = (
                    f"{self.path}/{self.case}/{self.name}_{file_template}.json"
                )
                os.system(f"grib_ls -p {parameters} -j {outfile} > {json_filename}")
                print(f" create TOC for {file_template} as {json_filename}")
                if re.match("^ec", file_to_scan):
                    os.remove(outfile)
            else:
                print(f" could not find {outfile}")

        os.environ["ECCODES_DEFINITION_PATH"] = f"{self.edp}"

    #########################################################################
    def check_file_type(self, infile):

        isgrib = True
        issfx = False
        grib_version = -1

        try:
            cmd = subprocess.Popen(
                ["codes_info", "-d"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except FileNotFoundError:
            print(" could not find codes_info, have you loaded a module for eccodes?")
            sys.exit()
        cmd_out, cmd_err = cmd.communicate()
        self.edp = cmd_out.decode("utf-8")

        if "ICMSH" in infile:
            isgrib = False
        elif "sfx" in infile:
            issfx = True
            grib_version = 1
        elif "grib2" in infile:
            grib_version = 2
            os.environ[
                "ECCODES_DEFINITION_PATH"
            ] = f"{os.getcwd()}/eccodes/definitions:{self.edp}"
            if self.printlev > 1:
                print(
                    f" Update ECCODES_DEFINITION_PATH:{os.environ['ECCODES_DEFINITION_PATH']}"
                )
        elif "grib" in infile:
            grib_version = 1
        elif "GRIBPF" in infile:
            grib_version = 2
        elif ".grb2" in infile:
            grib_version = 2
        else:
            print(f"Cannot recognize {infile}")
            sys.exit()

        return isgrib, issfx, grib_version

    #########################################################################
    def toc(self, printlev=None):
        if printlev is not None:
            self.printlev = printlev
        for fname in self.file_templates:
            if fname in self.data:
                content = self.data[fname]
                dates = [d for d in sorted(content)]
                if content[dates[-1]][0] is None:
                    file_to_scan = self.reconstruct(dates[-1], file_template=fname)[-1]
                else:
                    file_to_scan = self.reconstruct(
                        dates[-1], content[dates[-1]][-1], fname
                    )[-1]

                self.build_toc(fname, file_to_scan)

    #########################################################################
    def scan(self):

        print(" scan:", self.name)

        def subsub(path, subdirs, replace_keys):
            def pdir(x, replace_keys):
                y = x
                for k, v in replace_keys.items():
                    if k in y:
                        y = y.replace(k, v)
                return y

            result = []
            content = ecfs_scan(path)
            for cc in content:
                pp = pdir(subdirs[0], replace_keys)
                mm = [m.start() for m in re.finditer(pp, cc)]
                if len(mm) > 0:
                    if len(subdirs) > 1:
                        subresult = subsub(path + cc, subdirs[1:], replace_keys)
                    else:
                        subresult = [path + cc]
                    result.extend(subresult)

            return result

        print(
            "  Search for files named {} in {}".format(
                self.file_templates, self.path_template
            )
        )

        i = self.path_template.find("%")

        base_path = self.path_template[:i] if i > -1 else self.path_template
        part_path = self.path_template[i:] if i > -1 else ""

        if re.match("^ec", base_path):
            subdirs = self.path_template[i:].split("/")
            if subdirs[-1] == "":
                subdirs.pop()
            x, mk, replace_keys = self.check_template(part_path)
            dirs = subsub(base_path, subdirs, replace_keys)
            content = [d[i:] + cc for d in dirs for cc in ecfs_scan(d)]
        else:
            content = find_files(base_path)

        findings = {}
        signal = True
        for file_template in self.file_templates:
            tmp = {}
            x, mk, replace_keys = self.check_template(
                os.path.join(part_path, file_template)
            )
            for cc in content:
                zz = re.findall(r"" + x + "$", cc)
                if len(zz) > 0:
                    dtg, l = self.set_timestamp(mk, zz[0])
                    if dtg not in tmp:
                        tmp[dtg] = []
                    tmp[dtg].append(l)

            for k in tmp:
                tmp[k].sort()

            signal = signal and bool(tmp)
            findings[file_template] = tmp

        return findings, signal

    #########################################################################
    def set_timestamp(self, mk, z):
        list_keys = ("%Y", "%m", "%d", "%H", "%M", "%S")
        res = ["0"] * 6

        mk_list = list(mk)
        mk_len = len(mk_list)
        for j, l in enumerate(list_keys):
            for i, k in enumerate(mk):
                if l == k:
                    res[j] = z[i]
        dtg = datetime.strptime(":".join(res), "%Y:%m:%d:%H:%M:%S")

        leadtime = None
        times = []
        lh = None
        lm = None
        for k in mk:
            if k in ("%LLLL", "%LLL", "%LL"):
                i = mk_list.index(k) - mk_len
                times.append(3600 * int(z[i]))
            if k == "%LM":
                i = mk_list.index(k) - mk_len
                times.append(60 * int(z[i]))

        if len(times) > 0:
            leadtime = sum(times)

        return str(dtg), leadtime


#########################################################################
def ecfs_scan(path):

    cmd = subprocess.Popen(["els", path], stdout=subprocess.PIPE)
    cmd_out, cmd_err = cmd.communicate()

    # Decode and filter output
    res = [line.decode("utf-8") for line in cmd_out.splitlines()]
    return res


#########################################################################
def ecfs_copy(infile, outfile, printlev=0):

    args = ["ecp", infile, outfile]
    if printlev > 0:
        print(" "+" ".join(args))
    cmd = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cmd_out, cmd_err = cmd.communicate()

    if cmd_err is not None:
        if len(cmd_err) > 0:
            res = cmd_err.decode("utf-8")
            print(res)
            return False

    return False


#########################################################################
def hub(p, dtgs, leadtime=None):

    dtg = datetime.strptime(dtgs, "%Y-%m-%d %H:%M:%S")

    re_map = {
        "%Y": "{:04d}".format(dtg.year),
        "%m": "{:02d}".format(dtg.month),
        "%d": "{:02d}".format(dtg.day),
        "%H": "{:02d}".format(dtg.hour),
        "%M": "{:02d}".format(dtg.minute),
        "%S": "{:02d}".format(dtg.second),
    }

    if leadtime is not None:
        lh, lm = leadtime2hm(leadtime)

        re_map["%LLLL"] = "{:04d}".format(lh)
        re_map["%LLL"] = "{:03d}".format(lh)
        re_map["%LL"] = "{:02d}".format(lh)
        re_map["%LM"] = "{:02d}".format((lm))

    path = p
    for k, v in re_map.items():
        path = path.replace(k, str(v))

    return path


#########################################################################
def find_files(path, prefix=""):

    # Scan given path and subdirs and return files matching the pattern
    result = []
    try:
        it = os.scandir(path)
    except:
        it = []
    for entry in it:
        if not entry.name.startswith(".") and entry.is_file():
            if re.search(prefix, entry.name):
                result.append(entry.name)
        if not entry.name.startswith(".") and entry.is_dir():
            subresult = find_files(os.path.join(path, entry.name), prefix)
            subresult = [entry.name + "/" + e for e in subresult]
            result.extend(subresult)
    return result


#########################################################################
def leadtime2hm(leadtime):

    if isinstance(leadtime, str):
        lh = int(leadtime / 3600)
        lm = int(leadtime) % 3600 / 60
    elif isinstance(leadtime, float):
        lh = int(leadtime / 3600)
        lm = int(leadtime) % 3600 / 60
    elif isinstance(leadtime, int):
        lh = int(leadtime / 3600)
        lm = leadtime % 3600 / 60
    else:
        sys.exit()

    return lh, int(lm)

#########################################################################
def expand_dates(sdate, edate, step):
    # Construct a list of dates
    dates = []
    if sdate is not None and edate is not None:
        while sdate <= edate:
            dates.append(sdate)
            sdate += step

    return dates


#########################################################################
def expand_times(stime, etime, step):
    # Construct a list of lead_times
    leadtimes = None
    if stime is not None and etime is not None:
        leadtimes = []
        while stime <= etime:
            leadtimes.append(stime.days * 24 * 3600 + stime.seconds)
            stime += step

    return leadtimes
