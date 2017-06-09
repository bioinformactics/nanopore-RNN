#!/usr/bin/env python
"""
This is a place for small scripts and utility functions
"""
########################################################################
# File: utils.py
#  executable: utils.py
# Purpose: maintain some simple functions as needed
#   make sure all events are represented from output from signalalign

#   stderr: errors and status
#   stdout:
#
# Author: Andrew Bailey, Rojin Safavi
# History: 5/16/2017 Created
from __future__ import print_function
from timeit import default_timer as timer
import sys
import os
import re
import glob
import random
import boto
from error import PathError
import numpy as np
from Bio.Seq import Seq
# from Bio.Alphabet import generic_dna

#TODO create debug function and verbose options



def no_skipped_events(filepath):
    """Find if there are any skipped events in a signalalign file"""
    # this is quite slow but it works
    set1 = set()
    with open(filepath, 'r') as file_handle:
        for line in file_handle:
            set1.add(int(line.rstrip().split()[5]))
    return check_sequential(set1)

def check_sequential(list_of_integers):
    """Make sure there are no gaps in a list of integers"""
    # returns true if there are no gaps
    return bool(sorted(list_of_integers) == list(range(min(list_of_integers),\
     max(list_of_integers)+1)))

def grab_s3_files(bucket_path, ext=""):
    """Grab the paths to files with an extention in a s3 bucket or in a local directory"""
    # connect to s3
    bucket_path = bucket_path.split("/")
    conn = boto.connect_s3()
    test = conn.lookup(bucket_path[0])
    if test is None:
        print("There is no bucket with this name!", file=sys.stderr)
        return 1
    else:
        bucket = conn.get_bucket(bucket_path[0])
    file_paths = []
    # check file in each bucket
    for key in bucket.list("/".join(bucket_path[1:])):
        if ext == "":
            file_paths.append(os.path.join("s3://", bucket_path[0], key.name))
        else:
            if key.name.split(".")[-1] == ext:
                file_paths.append(os.path.join("s3://", bucket_path[0], key.name))
    return file_paths

def list_dir(path, ext=""):
    """get all file paths from local directory with extention"""
    if ext == "":
        onlyfiles = [os.path.join(os.path.abspath(path), f) for f in \
        os.listdir(path) if \
        os.path.isfile(os.path.join(os.path.abspath(path), f))]
    else:
        onlyfiles = [os.path.join(os.path.abspath(path), f) for f in \
        os.listdir(path) if \
        os.path.isfile(os.path.join(os.path.abspath(path), f)) \
        if f.split(".")[-1] == ext]
    return onlyfiles

def check_events(directory):
    """Check if all the tsv files from signal align match each event"""
    counter = 0
    good_files = []
    # make sure each file has all events
    for file1 in list_dir(directory, ext="tsv"):
        if no_skipped_events(file1):
            good_files.append(file1)
        else:
            counter += 1
    # print how many failed and return files that passed
    print("{} files had missing events".format(counter))
    return good_files

def project_folder():
    """Find the project folder path from any script"""
    current = os.path.abspath(__file__).split("/")
    path = '/'.join(current[:current.index("nanopore-RNN")+1])
    if os.path.exists(path):
        return path
    else:
        PathError("Path to directory does not exist!")

def get_project_file(localpath):
    """Get the path to an internal project file"""
    if localpath != "":
        if not localpath.startswith('/'):
            localpath = '/'+localpath
    path = os.path.join(project_folder()+localpath)
    if os.path.isfile(path):
        return path
    else:
        raise PathError("Path to file does not exist!")

def remove_fasta_newlines(reference_path, reference_modified_path):
    """Get fast5 file and remove \n from the ends"""
    with open(reference_modified_path, 'w') as outfile, open(reference_path, 'r') as infile:
        for line in infile:
            if ">" in line:
                outfile.write(line)
            else:
                line1 = line.rstrip()
                outfile.write(line1)

    return reference_modified_path

def get_complement(motif, reverse=False):
    """get the complement or reverse complement of a dna sequecnce"""
    dna = Seq(motif)
    if reverse:
        motif_complement = str(dna.reverse_complement())
    else:
        motif_complement = str(dna.complement())
    return motif_complement

# TODO This needs to work with the human genome so it probably cant read in the whole genome
def make_bed_file(reference_modified_path, bed_file_path, motifs={"CCAGG":"CEAGG", "CCTGG":"CETGG"}):
    """Create bed file from motif and replacement motif

    Must replace a single character with a new, non canonical base

    """
    reference = ""
    seq_name = ""
    # get reference sequence as string
    with open(reference_modified_path, 'r') as infile:
        for line in infile:
            if ">" in line:
                seq_name = seq_name + line.rsplit()[0].split(">")[1]
            else:
                reference = reference + line
    # create bed file
    with open(bed_file_path, "w") as output:
        for motif, replacement in motifs.items():
            # get replacement character
            pos = [i for i in range(len(motif)) if motif[i] != replacement[i]][0]
            old_char = motif[pos]
            new_char = replacement[pos]
            motif1_replaced = reference.replace(motif, replacement)
            motif1_position = [m.start() for m in re.finditer(new_char, motif1_replaced)]
            for i in motif1_position:
                output.write(seq_name + "\t" + np.str(i) + "\t" + "+" + "\t" +
                             old_char +"\t" + new_char + "\n")
            # find motifs on opposite strand
            replace_pos = len(motif)-pos-1
            motif1_comp = get_complement(motif, reverse=True)
            # replace motif complement with modified base at correct position
            modified_motif1_comp = motif1_comp[:replace_pos] + new_char + \
                                   motif1_comp[replace_pos+1:]
            motif1_comp_replaced = reference.replace(motif1_comp, modified_motif1_comp)
            motif1_comp_position = [m.start() for m in re.finditer(new_char, motif1_comp_replaced)]
            for i in motif1_comp_position:
                output.write(seq_name + "\t" + np.str(i) + "\t" + "-" + "\t" +
                             old_char +"\t" + new_char + "\n")

## Concatenate control and experimental assignments
def concatenate_assignments(assignments_path1, assignments_path2, output):
    """concatenates control and experimental assignments"""
    read_files = glob.glob(assignments_path1 + "/*.assignments") + glob.glob(assignments_path2 + "/*.assignments")
    with open(output, "w") as outfile:
        for f in read_files:
            with open(f, "rb") as infile:
                outfile.write(infile.read())

def get_sample_assignments(concatenated_assignmnets_path, sampled_assignments):
    """for each kmer in assignmnets get 50 assignment or less"""
    kmerDict = dict()
    with open(concatenated_assignmnets_path, "r") as infile:
        for i in infile:
            key = i.split("\t")[0]
            value = "\t".join(i.split("\t")[1:])
            if kmerDict.has_key(key):
                kmerDict[key].append(value)
            else:
                kmerDict[key] = [value]
    with open(sampled_assignments, "w") as outfile:
        for key, value in kmerDict.iteritems():
            mylist = kmerDict[key]
            if len(mylist) >= 50:
                rand_smpl = [mylist[i] for i in random.sample(range(len(mylist)), 50)]
                for g in rand_smpl:
                    string = ''.join(g)
                    outfile.write(key + "\t" + string)
            elif len(mylist) < 50:
                rand_smpl = [mylist[i] for i in random.sample(range(len(mylist)), len(mylist))]
                for g in rand_smpl:
                    string = ''.join(g)
                    outfile.write(key + "\t" + string)

def sum_to_one(vector):
    """Make sure a vector sums to one, if not, create diffuse vector"""
    total = sum(vector)
    if total != 1:
        if total > 1:
            # NOTE Do we want to deal with vectors with probability over 1?
            pass
        else:
            # NOTE this is pretty slow so maybe remove it?
            leftover = 1 - total
            amount_to_add = leftover/ (len(vector) - np.count_nonzero(vector))
            for index, prob in enumerate(vector):
                if prob == 0:
                    vector[index] = amount_to_add
    return vector

def add_field(np_struct_array, descr):
    """Return a new array that is like the structured numpy array, but has additional fields.
    descr looks like descr=[('test', '<i8')]
    """
    if np_struct_array.dtype.fields is None:
        raise ValueError("Must be a structured numpy array")
    new = np.zeros(np_struct_array.shape, dtype=np_struct_array.dtype.descr + descr)
    for name in np_struct_array.dtype.names:
        new[name] = np_struct_array[name]
    return new

def merge_two_dicts(dict1, dict2):
    """Given two dicts, merge them into a new dict as a shallow copy.
    source: https://stackoverflow.com/questions/38987/
    how-to-merge-two-python-dictionaries-in-a-single-expression"""
    final = dict1.copy()
    final.update(dict2)
    return final



def main():
    """Test the methods"""
    start = timer()

    ref_seq = get_project_file("/testing/reference-sequences/ecoli_k12_mg1655.fa")
    reference_modified_path = project_folder()+"/testing/reference-sequences/ecoli_k12_mg1655_modified.fa"
    remove_fasta_newlines(ref_seq, reference_modified_path)
    bed_file_path = project_folder()+"/testing/reference-sequences/CCAGG_modified.bed"
    motifs = {"CCAGG":"CEAGG", "CCTGG":"CETGG"}

    make_bed_file(reference_modified_path, bed_file_path, motifs)
    stop = timer()
    print("Running Time = {} seconds".format(stop-start), file=sys.stderr)

if __name__ == "__main__":
    main()
    raise SystemExit
