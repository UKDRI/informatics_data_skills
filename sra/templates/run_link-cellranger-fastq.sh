#!/bin/bash
#
#SBATCH --job-name=sra-tools_link-cellranger        # Job name
#SBATCH --partition=__PARTITION__    # Partition or queue name
#SBATCH --nodes=1                     # Number of nodes
#SBATCH --ntasks-per-node=1           # Number of tasks per node
#SBATCH --cpus-per-task=2             # Number of CPU cores per task (I/O only)
#SBATCH --time=__LINK_TIME__                # Maximum runtime (D-HH:MM:SS)
set -e
set -o pipefail


# Directory holding the fasterq-dump output (<SRR>_1.fastq.gz ... <SRR>_4.fastq.gz)
indir=__FASTQ_DIR__
# Where the cellranger-named symlinks are created (may be the same as indir)
linkdir=__LINK_DIR__

# Which two dumped files are the 10x cDNA read pair, as <R1>,<R2>.
# `fasterq-dump --include-technical --split-files` numbers its output positionally,
# so for 10x the real pair is the LAST TWO files, not _1/_2:
#   2 files  _1=R1         _2=R2                              -> readmap=1,2
#   3 files  _1=I1  _2=R1  _3=R2  (single index)              -> readmap=2,3
#   4 files  _1=I1  _2=I2  _3=R1  _4=R2  (dual index, e.g.
#                                         Chromium 5')        -> readmap=3,4
# This is DECLARED, never detected. COUNT THE DUMPED FILES FOR ONE RUN AND SET IT
# BEFORE SUBMITTING -- a wrong value yields plausible-looking garbage counts, not
# an error. The read lengths printed below are the check.
readmap=__READ_MAP__

r1=${readmap%,*}
r2=${readmap#*,}

if [ ! -d $linkdir ]
then
        mkdir -p $linkdir
        echo "Created '$linkdir'."
fi


# First read's length in a FASTQ file; handles .fastq and .fastq.gz. The `|| true`
# absorbs the SIGPIPE that awk's `exit` sends to zcat, which `set -o pipefail`
# would otherwise turn into a job failure.
readlen()
{
        { zcat -f -- $1 2>/dev/null || true; } | awk 'NR == 2 { print length($0); exit }'
}

# Path of dumped read $2 for run $1, preferring the gzipped file. Empty if absent.
readpath()
{
        if [ -e $indir/${1}_${2}.fastq.gz ]
        then
                echo $indir/${1}_${2}.fastq.gz
        elif [ -e $indir/${1}_${2}.fastq ]
        then
                echo $indir/${1}_${2}.fastq
        fi
}


# Glob the dump output directory, like run_fasterq-dump.sh globs the .sra dir.
# NOTE this links every run present in $indir under the one readmap above.
ids=$(find $indir/ -maxdepth 1 \( -name \*_[1-4].fastq -o -name \*_[1-4].fastq.gz \) \
        | sed -E 's|.*/||; s/_[1-4]\.fastq(\.gz)?$//' | sort -u)

if [ -z "$ids" ]
then
        >&2 echo "ERROR! No <run>_[1-4].fastq[.gz] found in '$indir'. Run run_fasterq-dump.sh first."
        exit 1
fi

linked=0
skipped=0

for id in $ids
do
        src1=$(readpath $id $r1)
        src2=$(readpath $id $r2)

        if [ -z "$src1" ] || [ -z "$src2" ]
        then
                >&2 echo "WARN. '$id': read _${r1} and/or _${r2} is missing -- is readmap=$readmap right? SKIPPING."
                ls -1 $indir/${id}_[1-4].fastq* >&2 || true
                skipped=$((skipped + 1))
                continue
        fi

        # 10x R1 is the 24-32 bp barcode+UMI read, R2 the longer cDNA read.
        len1=$(readlen $src1)
        len2=$(readlen $src2)
        echo "$id: R1 <- _${r1} (${len1:-?} bp), R2 <- _${r2} (${len2:-?} bp)"
        if [ -n "$len1" ] && { [ $len1 -lt 24 ] || [ $len1 -gt 32 ]; }
        then
                >&2 echo "WARN. '$id': R1 is ${len1} bp, expected 24-32 bp (16 bp barcode + 10-12 bp UMI)."
                >&2 echo "      Check readmap=$readmap against the dumped files:"
                ls -1 $indir/${id}_[1-4].fastq* >&2 || true
        fi

        ext1=fastq.gz
        ext2=fastq.gz
        case $src1 in *.fastq) ext1=fastq;; esac
        case $src2 in *.fastq) ext2=fastq;; esac
        if [ $ext1 = fastq ] || [ $ext2 = fastq ]
        then
                >&2 echo "WARN. '$id' is not gzipped -- nf-core and cellranger expect .fastq.gz."
        fi

        # Illumina/bcl2fastq convention: <sample>_S1_L001_R{1,2}_001.fastq.gz.
        # cellranger's own FASTQ parser requires this shape (a bare _R1 is NOT
        # matched); nf-core/scrnaseq accepts it too, so one name serves both.
        # The prefix is the RUN accession -- what the dumped files are named.
        dst1=$linkdir/${id}_S1_L001_R1_001.$ext1
        dst2=$linkdir/${id}_S1_L001_R2_001.$ext2

        clobber=0
        for dst in $dst1 $dst2
        do
                if [ -e $dst ] && [ ! -L $dst ]
                then
                        >&2 echo "WARN. '$dst' exists and is not a symlink. NOT replacing it."
                        clobber=1
                fi
        done
        if [ $clobber -eq 1 ]
        then
                skipped=$((skipped + 1))
                continue
        fi

        # -s symlink, -f replace, -n don't follow an existing link, -r relative
        # target (so the directory stays relocatable). Idempotent: safe to re-run.
        ln -sfnr $src1 $dst1
        ln -sfnr $src2 $dst2
        linked=$((linked + 1))
done

echo "Linked $linked run(s) in '$linkdir' as <run>_S1_L001_R{1,2}_001.fastq.gz (readmap=$readmap)."
if [ $skipped -gt 0 ]
then
        >&2 echo "ERROR! $skipped run(s) got no R1/R2 link -- see the WARNings above."
        >&2 echo "       Fix readmap and re-run; runs already linked are left untouched."
        exit 1
fi
echo "ALL DONE."
