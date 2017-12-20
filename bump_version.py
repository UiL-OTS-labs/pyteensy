#!/usr/bin/env python3

'''
This script is a utility to get the current pyteensy version, and to modify it.
The script reads pyteensy-version.py and modifies it. This program should modify
all files that needs to be changed when the pyteensy version changes.

This file is a utility in order to maintain and build pyteensy, it is however
not a source of pyteensy itself.

pyteensy tries to live to the rule that a minor version that is stable ends with
an even number.
''' 

import argparse
import re

#handle cmd arguments
ap = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
ap.add_argument('--major', help="bump the major version", action="store_true")
ap.add_argument('--minor', help="bump the minor version", action="store_true")
ap.add_argument('--micro', help="bump the micro version", action="store_true")
ap.add_argument('--set-major',  help="set the major version", type=int, default=-1)
ap.add_argument('--set-minor',  help="set the minor version", type=int, default=-1)
ap.add_argument('--set-micro',  help="set the micro version", type=int, default=-1)

#versions
current_major = -1
current_minor = -1
current_micro = -1

# regular expresions to find the versioning info in pyteensy-version.py
re_major = re.compile(r'^pyteensy_major\s*=\s*(\d+)$', re.M)
re_minor = re.compile(r'^pyteensy_minor\s*=\s*(\d+)$', re.M)
re_micro = re.compile(r'^pyteensy_micro\s*=\s*(\d+)$', re.M)

# the versioning file
versionfile = 'pyteensy-version.py'

# contents of the versioning file.
version_content = ""

def update_pyteensy_version():
    '''
    Update pyteensy-version.py
    This file is the file that maintains the final version info
    and is the leading source to what is the actual version of pyteensy.
    '''

    content = str(version_content)

    #replacement strings
    majorstr = "pyteensy_major = {0}".format(current_major)
    minorstr = "pyteensy_minor = {0}".format(current_minor)
    microstr = "pyteensy_micro = {0}".format(current_micro)
    
    content, n = re_major.subn(majorstr ,content, 1)
    assert(n == 1)
    content, n = re_minor.subn(minorstr, content, 1)
    assert(n == 1)
    content, n = re_micro.subn(microstr, content, 1)
    assert(n == 1)

    f = None
    try:
        f = open(versionfile, 'w')
        f.write(content)
        f.close()
    except :
        exit("unable to open " + versionfile + " for writing" )

def update_versioning_files():
    ''' update all version files. '''
    update_pyteensy_version()

def get_version():
    ''' returns a string with pyteensy + the current version.'''
    return "pyteensy-" + str(current_major) + "." + str(current_minor) +\
                "." + str(current_micro)

def get_version_info():
    '''
    this function read pyteensy-version.py to obtain the current version
    info.
    '''
    
    global current_major
    global current_minor
    global current_micro
    global version_content

    f = None
    try :
        f = open(versionfile,  'r')
    except IOError:
        exit ("Unable to open " + versionfile)

    version_content = f.read();
    if not version_content:
        exit(versionfile + "is empty.")

    mmajor = re_major.search(version_content)
    mminor = re_minor.search(version_content)
    mmicro = re_micro.search(version_content)

    if mmajor and mminor and mmicro :
        current_major = int(mmajor.group(1))
        current_minor = int(mminor.group(1))
        current_micro = int(mmicro.group(1))
    else:
        exit(versionfile + " is in an unexpected format.")

def bump_micro_version():
    '''
    bump microversion
    '''
    global current_micro
    current_micro +=1

def bump_minor_version():
    '''
    bump minorversion and set micro version to 0 
    '''
    global current_minor
    global current_micro
    current_micro = 0
    current_minor += 1

def bump_major_version():
    '''
    bump minorversion and set micro and minor version to 0 
    '''
    global current_minor
    global current_micro
    global current_major
    current_micro = 0
    current_minor = 0
    current_major += 1

if __name__ == "__main__":

    ns = ap.parse_args()
    get_version_info()
    print ("Current version: " + get_version())

    bump    = ns.major or ns.minor or ns.micro
    setting = ns.set_major >= 0 or ns.set_minor >= 0 or ns.set_micro >= 0

    # bump specific versions 
    if ns.micro:
        bump_micro_version()
    if ns.minor:
        bump_minor_version()
    if ns.major:
        bump_major_version()

    # set versions explicitly
    if ns.set_major >= 0:
        current_major = ns.set_major
    if ns.set_minor >= 0:
        current_minor = ns.set_minor
    if ns.set_micro >= 0:
        current_micro = ns.set_micro

    # write to output
    if bump or setting:
        update_versioning_files();
        print ("New version: " + get_version())

