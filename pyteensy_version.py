#!/usr/bin/env python3

'''
This file should not be editted by hand. Typically it is modified by using the
'bump-version.py' script. It reflects the build version of pyteensy. The
minor version number should be odd for nightly build and even for stable builds.
'''

name = "pyteensy"

pyteensy_major = 0
pyteensy_minor = 0
pyteensy_micro = 0

def get_version_major():
    return pyteensy_major

def get_version_minor():
    return pyteensy_minor

def get_version_micro():
    return pyteensy_micro

def get_version():
    return name + "-" + str(pyteensy_major) + "." +         \
            str(pyteensy_minor) + "." + str(pyteensy_micro)
