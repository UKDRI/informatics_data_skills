#!/bin/bash
#
#SBATCH --job-name=sra-tools_fasterq-dump        # Job name
#SBATCH --partition=__PARTITION__    # Partition or queue name
#SBATCH --nodes=1                     # Number of nodes
#SBATCH --ntasks-per-node=1           # Number of tasks per node
#SBATCH --cpus-per-task=__CPUS__             # Number of CPU cores per task
#SBATCH --time=__TIME__                # Maximum runtime (D-HH:MM:SS)
set -e
set -o pipefail


# Input directory containing .sra files (the prefetch output directory)
indir=__FASTQ_INDIR__
# Output directory for the extracted FASTQ files
outdir=__FASTQ_DIR__

# sra-tools image: a local .sif path, or a docker://<image> URI (apptainer pulls it)
sif=__IMAGE__
ncpu=__NCPU__

if [ ! -d $outdir ]
then
        mkdir -p $outdir
        echo "Created '$outdir'."
fi


for f in $(find $indir/ -name \*.sra)
do
        sraf=$(readlink -f $f)

        id=$(basename $sraf)
        id=${id%.sra}

        if [ ! -e $outdir/${id}_2.fastq ] && [ ! -e $outdir/${id}_2.fastq.gz ]
        then
                echo "Processing '$id': '$sraf'..."
                apptainer exec -B /nfsdata,/data,/shared $sif fasterq-dump $sraf --include-technical --split-files --threads $ncpu -O $outdir
        else
                echo "INFO. FastQ files already exists. SKIPPING '$id."
        fi
        if [ -e $outdir/${id}_1.fastq ]
        then
                pigz -p $ncpu $outdir/${id}_1.fastq
        fi
        if [ -e $outdir/${id}_2.fastq ]
        then
                pigz -p $ncpu $outdir/${id}_2.fastq
        fi
        if [ -e $outdir/${id}_3.fastq ]
        then
                pigz -p $ncpu $outdir/${id}_3.fastq
        fi
        echo "Done."
done
echo "ALL DONE."
