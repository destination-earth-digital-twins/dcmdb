#!/bin/bash
# The job name
#SBATCH --job-name=lumi_transfer
# Set the initial working directory
#SBATCH --chdir=.
# Choose the queue
#SBATCH --qos=nf
# Wall clock time limit
#SBATCH --time=24:00:00
# This is the job

module load python3

python3 transfer2lumi.py -c transfer.yml
