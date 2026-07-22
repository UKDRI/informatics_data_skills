#!/bin/bash
#
#SBATCH --job-name=sra-tools_prefetch        # Job name
#SBATCH --partition=__PARTITION__    # Partition or queue name
#SBATCH --nodes=1                     # Number of nodes
#SBATCH --ntasks-per-node=1           # Number of tasks per node
#SBATCH --cpus-per-task=__CPUS__             # Number of CPU cores per task
#SBATCH --time=__TIME__                # Maximum runtime (D-HH:MM:SS)
set -e
set -o pipefail


# SRR accession list (one accession per line, e.g. SRR_Acc_List.txt)
sralistf=__SRR_LIST__
# Output directory for prefetched .sra files (feeds fasterq-dump as its input)
outdir=__PREFETCH_DIR__
# sra-tools image: a local .sif path, or a docker://<image> URI (apptainer pulls it)
sif=__IMAGE__

if [ ! -d $outdir ]
then
        mkdir -p $outdir
        echo "Created '$outdir'."
else
        >&2 echo "ERROR! '$outdir' exists. Remove directory and run again."
        exit 1
fi


# INCREASE --max-size FOR LARGE SRR FILES
echo "Running prefetch..."

awk '{ print $1 }' $sralistf | xargs -i apptainer exec -B /nfsdata,/data,/shared $sif prefetch --max-size __MAXSIZE__ -O $outdir {}

echo "ALL DONE."
