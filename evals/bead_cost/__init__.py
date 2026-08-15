"""Present so that `unittest discover -s evals` descends into this directory.

The modules here are run as scripts and import each other through `sys.path`, so nothing else needs
a package. Without this file the tests beside them are silently not collected, and a suite that
skips a directory reports the same green as one that passed it.
"""
