# HQ XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# HQ X
# HQ X   quippy: Python interface to QUIP atomistic simulation library
# HQ X
# HQ X   Copyright James Kermode 2010
# HQ X
# HQ X   These portions of the source code are released under the GNU General
# HQ X   Public License, version 2, http://www.gnu.org/copyleft/gpl.html
# HQ X
# HQ X   If you would like to license the source code under different terms,
# HQ X   please contact James Kermode, james.kermode@gmail.com
# HQ X
# HQ X   When using this software, please cite the following reference:
# HQ X
# HQ X   http://www.jrkermode.co.uk/quippy
# HQ X
# HQ XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Set matplotlib in interactive mode with the TkAgg backend
# THESE MUST BE THE FIRST MATPLOTLIB COMMANDS CALLED!
import matplotlib
matplotlib.use('TkAgg')
matplotlib.interactive(True)

# Bring all of the numeric and plotting commands to the toplevel namespace
from pylab import *

from numpy import *
import quippy
from quippy import *

print """Welcome to quippy!

help(numpy) -> help on NumPy, Python's basic numerical library.
help(plotting) -> help on plotting commands.
help(quippy) -> help on quippy commands
"""
