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

"""Various subclasses to add functionality to automatically generated classes."""

import sys

major, minor = sys.version_info[0:2]

assert (major, minor) >= (2, 4)

if (major, minor) < (2, 5):
   import md5
   got_hashlib = False
else:
   import hashlib
   got_hashlib = True

import numpy, os, weakref
from farray import *

from quippy import FortranAtoms, FortranDictionary, FortranTable, FortranDynamicalSystem, FortranCInOutput, FortranPotential
from quippy import AtomsReaders, AtomsWriters

class NeighbourInfo(object):
   __slots__ = ('j','distance','diff','cosines','shift')

   def __init__(self, j, distance, diff, cosines, shift):
      self.j = j
      self.distance = float(distance)
      self.diff = diff.copy()
      self.cosines = cosines.copy()
      self.shift = shift.copy()

   def __int__(self):
      return self.j

   def __repr__(self):
      return 'NeighbourInfo(j=%d, distance=%f, diff=%s, cosines=%s, shift=%s)' % (self.j, self.distance, self.diff, self.cosines, self.shift)


class Neighbours(object):

   def __init__(self, at, hysteretic=False):
      self.atref = weakref.ref(at)
      self.hysteretic = hysteretic

   def __iter__(self):
      return self.iterneighbours()

   def iterneighbours(self):
      at = self.atref()

      for i in frange(at.n):
         yield self[i]

   def __getitem__(self, i):

      at = self.atref()
      if self.hysteretic:
         connect = at.hysteretic_connect
      else:
         connect = at.connect

      if not connect.initialised:
         if self.hysteretic:
            at.calc_connect_hysteretic(connect)
         else:
            at.calc_connect(connect)

      distance = farray(0.0)
      diff = fzeros(3)
      cosines = fzeros(3)
      shift = fzeros(3,dtype=numpy.int32)

      res = []
      for n in frange(at.n_neighbours(i,alt_connect=connect)):
         j = at.neighbour(i, n, distance, diff, cosines, shift, alt_connect=connect)
         res.append(NeighbourInfo(j,distance,diff,cosines,shift))

      return farray(res) # to give 1-based indexing      

   def distances(self, Z1=None, Z2=None):
      """Distances between pairs of neighbours, optionally filtered by species (Z1,Z2)"""
      at = self.atref()
      for i in frange(at.n):
         for neighb in self[i]:
            if neighb.j > i: continue
            if Z1 is not None and Z2 is not None:
               if sorted((at.z[i],at.z[neighb.j])) == sorted((Z1,Z2)):
                  yield neighb.distance
            else:
               yield neighb.distance

class Atom(dict):
   def __init__(self, *args, **kwargs):
      dict.__init__(self, *args, **kwargs)

   def __getattr__(self, key):
      return self[key]

   def __setattr__(self, key, value):
      raise ValueError('Atom instances are read-only')
      
   def __repr__(self):
      return 'Atom(%s)' % ', '.join(['%s=%r' % (k,v) for (k, v) in self.iteritems()])

   def __eq__(self, other):
      tol = 1e-8

      self_ = dict([(k.lower(),v) for (k,v) in self.iteritems() if k != 'i'])
      other_ = dict([(k.lower(),v) for (k,v) in other.iteritems() if k != 'i'])

      if sorted(self_.keys()) != sorted(other_.keys()): return False
      
      for k in self_.keys():
         v1, v2 = self_[k], other_[k]
         if isinstance(v1, FortranArray):
            if abs(v1 - v2).max() > tol:
               return False
         else:
            if v1 != v2:
               return False
      return True

   def __ne__(self, other):
      return not self.__eq__(other)


class Atoms(FortranAtoms):
   """
   Thin pythonic wrapper over auto-generated FortranAtoms class
   
   An atoms object contains atomic numbers, all dynamical variables
   and connectivity information for all the atoms in the simulation cell.
   It is initialised like this:
   >         call initialise(MyAtoms,N,lattice)
   where 'N' is the number of atoms to allocate space for and 'lattice' is a $3\times3$
   matrix of lattice vectors given as column vectors.
   
   Atoms also contains a Connection object, which stores distance information about
   the atom neghbours after 'calc_connect' has been called. Rather than using a minimum
   image convention, all neighbours are stored up to a radius of 'cutoff', including images
   """

   def __new__(cls, source=None, n=0, lattice=fidentity(3), fpointer=None, finalise=True,
                properties=None, params=None, fixed_size=False, *readargs, **readkwargs):
      """
      Initialise an Atoms object.

      The arguments, n, lattice, fpointer, finalise, data, properties and params are passed on
      to the FortranAtoms constructor.

      If source is given, Atoms.read(source, frame=frame) is called.
      """

      if source is None:
         self = object.__new__(cls)
      elif isinstance(source, cls):
         self = cls.copy(source)
      else:
         self = cls.read(source, *readargs, **readkwargs)

      return self

   def __init__(self, source=None, n=0, lattice=fidentity(3), fpointer=None, finalise=True,
                properties=None, params=None, fixed_size=False, *readargs, **readkwargs):
      if source is None:
         if params is not None and not isinstance(params, Dictionary):
            params = Dictionary(params)
         if properties is not None and not isinstance(properties, Dictionary):
            properties = Dictionary(properties)
         FortranAtoms.__init__(self, n=n, lattice=lattice, fpointer=fpointer, finalise=finalise,
                               properties=properties, params=params, fixed_size=fixed_size)
         self.neighbours = Neighbours(self)
         self.hysteretic_neighbours = Neighbours(self,hysteretic=True)

   @classmethod
   def read(cls, source, format=None, *args, **kwargs):
      if format is None:
         if isinstance(source, str):
            if source in AtomsReaders:
               format = source
            else:
               base, ext = os.path.splitext(source)
               format = ext[1:]
         else:
            format = source.__class__

      opened = False
      if format in AtomsReaders:
         source = AtomsReaders[format](source, *args, **kwargs)
         opened = True

      if not hasattr(source, '__iter__'):
         raise ValueError('Cannot read from source %r - not an iterator' % source)
      at = iter(source).next()
      if not isinstance(at, cls):
         raise ValueError('Object %r read from source %r is not Atoms instance' % (at, source))
      if opened and hasattr(source, 'close'):
         source.close()
      return at
         

   def write(self, dest, format=None, properties=None, prefix=None, *args, **kwargs):
      opened = False
      if format is None:
         if isinstance(dest, str):
            opened = True
            if dest in AtomsWriters:
               format = dest
            else:
               base, ext = os.path.splitext(dest)
               format = ext[1:]
         else:
            format = dest.__class__

      if format in AtomsWriters:
         dest = AtomsWriters[format](dest, *args, **kwargs)

      if not hasattr(dest, 'write'):
         raise ValueError("Don't know how to write to destination \"%s\" in format \"%s\"" % (dest, format))

      write_kwargs = {}
      if properties is not None: write_kwargs['properties'] = properties
      if prefix is not None: write_kwargs['prefix'] = prefix
      try:
         res = dest.write(self, **write_kwargs)
      except TypeError:
         raise ValueError('Atoms.write destination %r does not specifying arguments %r' % (dest, kwargs))

      if opened and hasattr(dest, 'close'):
         dest.close()
      return res


   def show(self, property=None, highlight=None, arrows=None, *arrowargs, **arrowkwargs):
      """Show this Atoms object in AtomEye."""
      try:
         import atomeye
         atomeye.show(self,property=property, highlight=highlight, arrows=arrows, *arrowargs, **arrowkwargs)
      except ImportError:
         raise RuntimeError('AtomEye not available')

   def select(self, mask=None, list=None):
      """Select a subset of the atoms in an atoms object

      Use either a logical mask array or a list of atom indices to include.

      small_at = at.select([mask, list])
      
      """
      if mask is not None:
         mask = farray(mask)
         out = Atoms(n=mask.count(),lattice=self.lattice)
         FortranAtoms.select(out, self, mask=mask)
      elif list is not None:
         list = farray(list)
         out = Atoms(n=len(list), lattice=self.lattice)
         FortranAtoms.select(out, self, list=list)
      else:
         raise ValueError('Either mask or list must be present.')
      return out

   def copy(self):
      other = Atoms(n=self.n, lattice=self.lattice, 
                    properties=self.properties, params=self.params)
      other.use_uniform_cutoff = self.use_uniform_cutoff
      other.cutoff = self.cutoff
      other.cutoff_break = self.cutoff_break
      other.nneightol = self.nneightol
      return other


   def calc_bonds(self):
      if hasattr(self, '_bonds'): return
      
      if not self.connect.initialised:
         self.calc_connect()
         
      self._bonds = []
      from matplotlib.lines import Line2D
      for i in frange(self.n):
         for n in frange(self.n_neighbours(i)):
            if self.is_nearest_neighbour(i, n):
               j = self.neighbour(i, n)
               self._bonds.append(Line2D((self.pos[1,i],self.pos[1,j]), (self.pos[2,i],self.pos[2,j]),zorder=-100))

   def plot(self, bonds=False, **kwargs):
      import pylab

      ax = pylab.gca()
      ax.scatter(self.pos[1,:],self.pos[2,:], **kwargs)

      if bonds:
         self.calc_bonds()
         for line in self._bonds:
            ax.add_line(line)

      pylab.gcf().show()

   def plot_arrows(self, value):

      import pylab
      pylab.quiver(numpy.array(self.pos[1,:]),numpy.array(self.pos[2,:]),
                   numpy.array(value[1,:]),numpy.array(value[2,:]))

   def __len__(self):
      return self.n

   def __getattr__(self, name):
      try:
         return self.properties[name]
      except KeyError:
         try:
            return self.params[name]
         except KeyError:
            raise AttributeError('Unknown Atoms attribute %s' % name)

   def __getitem__(self, i):
      if i < 1 or i > self.n:
         raise ValueError('Atoms index should be in range 1..self.n(%d)' % self.n)
      res = {}
      res['i'] = i
      for k in self.properties.keys():
         v = getattr(self,k.lower())[...,i]
         if isinstance(v,FortranArray):
            if v.dtype.kind == 'S':
               v = ''.join(v).strip()
            elif v.shape == ():
               v = v.item()
         res[k.lower()] = v

      return Atom(**res)

   def __setitem__(self, i, atom):
      if i < 1 or i > self.n:
         raise ValueError('Atoms index should be in range 1..self.n(%d)' % self.n)
      for k, v in atom.iteratoms():
         setattr(self, k.lower())[...,i] = v
      

   def __eq__(self, other):
      tol = 1e-8
      if self.n != other.n: return False
      if abs(self.lattice - other.lattice).max() > tol: return False
      if self.params != other.params: return False
      if self.properties != other.properties: return False
      return True

   def __ne__(self, other):
      return not self.__eq__(other)


   def density(self):
      from quippy import ElementMass, N_A, MASSCONVERT
      
      """Density in units of :math:`g/m^3`. If `mass` property exists, use that, otherwise we use `z`"""
      if hasattr(self, 'mass'):
         mass = sum(self.mass)/MASSCONVERT/1.0e3
      else:
         mass = sum(ElementMass[z] for z in self.z)/1.0e3

      return mass/(N_A*self.cell_volume()*1.0e-30)/1.0e3


   def add_property(self, name, value, n_cols=None, overwrite=None, property_type=None):
      """
      Add a new property to this Atoms object.

      `name` is the name of the new property and `value` should be
      either a scalar or an array representing the value, which should
      be either integer, real, logical or string.

      If a scalar is given for `value` it is copied to every element
      in the new property.  `n_cols` can be specified to create a 2D
      property from a scalar initial value - the default is 1 which
      creates a 1D property.

      If an array is given for `value` it should either have shape
      (self.n,) for a 1D property or (n_cols,self.n) for a 2D
      property.  In this case `n_cols` is inferred from the shape of
      the `value` and shouldn't be passed as an argument.

      If `property_type` is present, then no attempt is made to
      infer the type from `value`. This is necessary to resolve
      ambiguity between integer and logical types.

      If property with the same type is already present then no error
      occurs.If `overwrite` is true, the value will be overwritten with
      that given in `value`, otherwise the old value is retained.
      """

      kwargs = {}
      if n_cols is not None: kwargs['n_cols'] = n_cols
      if overwrite is not None: kwargs['overwrite'] = overwrite

      if property_type is None:
         FortranAtoms.add_property(self, name, value, **kwargs)

      else:
         # override value_ref if property_type is specified
         
         from quippy import (T_INTEGER_A, T_REAL_A, T_LOGICAL_A, T_CHAR_A,
                             T_INTEGER_A2, T_REAL_A2)

         new_property = not self.has_property(name)
         
         type_to_value_ref = {
            T_INTEGER_A  : 0,
            T_REAL_A : 0.0,
            T_CHAR_A  : " ",
            T_LOGICAL_A : False,
            T_INTEGER_A2 : 0,
            T_REAL_A2: 0.0
            }
         try:
            value_ref = type_to_value_ref[property_type]
         except KeyError:
            raise ValueError('Unknown property_type %d' % property_type)

         FortranAtoms.add_property(self, name, value_ref, **kwargs)
         if new_property or overwrite:
            getattr(self, name.lower())[:] = value            

from dictmixin import DictMixin, ParamReaderMixin

from quippy import (T_NONE, T_INTEGER, T_REAL, T_COMPLEX,
                    T_CHAR, T_LOGICAL, T_INTEGER_A,
                    T_REAL_A, T_COMPLEX_A, T_CHAR_A,
                    T_LOGICAL_A, T_INTEGER_A2, T_REAL_A2)

class Dictionary(DictMixin, ParamReaderMixin, FortranDictionary):

   __doc__ = FortranDictionary.__doc__

   _interfaces = FortranDictionary._interfaces
   _interfaces['set_value'] = [ k for k in FortranDictionary._interfaces['set_value'] if k[0] != 'set_value_s_a' ]

   _scalar_types = (T_INTEGER, T_REAL, T_COMPLEX, T_LOGICAL, T_CHAR)

   _array_types  = (T_INTEGER_A, T_REAL_A, T_COMPLEX_A, T_CHAR_A,
                    T_LOGICAL_A, T_INTEGER_A2, T_REAL_A2)

   def __init__(self, D=None, *args, **kwargs):
      FortranDictionary.__init__(self, *args, **kwargs)
      self._cache = {}
      if D is not None:
         self.read(D) # copy from D

   def keys(self):
      return [self.get_key(i).strip() for i in frange(self.n)]

   def has_key(self, key):
      return key.lower() in [k.lower() for k in self.keys()]

   def get_value(self, k):
      "Return a _copy_ of a value stored in Dictionary"
      if not k in self:
         raise KeyError('Key "%s" not found ' % k)

      t, s, s2 = self.get_type_and_size(k)

      if t == T_NONE:
         raise ValueError('Key %s has no associated value' % k)
      elif t == T_INTEGER:
         v,p = self._get_value_i(k)
      elif t == T_REAL:
         v,p = self._get_value_r(k)
      elif t == T_COMPLEX:
         v,p = self._get_value_c(k)
      elif t == T_CHAR:
         v,p = self._get_value_s(k)
         v = v.strip()
      elif t == T_LOGICAL:
         v,p = self._get_value_l(k)
         v = bool(v)
      elif t == T_INTEGER_A:
         v,p = self._get_value_i_a(k,s)
      elif t == T_REAL_A:
         v,p = self._get_value_r_a(k,s)
      elif t == T_COMPLEX_A:
         v,p = self._get_value_c_a(k,s)
      elif t == T_CHAR_A:
         v,p = self._get_value_s_a2(k,s2[1], s2[2])
         v = v[...,1]  # Last index is length of string, here fixed to 1
         v.strides = (1, v.shape[0])  # Column-major storage
      elif t == T_LOGICAL_A:
         v,p = self._get_value_l_a(k,s)
         v = farray(v, dtype=bool)
      elif t == T_INTEGER_A2:
         v,p = self._get_value_i_a2(k, s2[1], s2[2])
      elif t == T_REAL_A2:
         v,p = self._get_value_r_a2(k, s2[1], s2[2])
      else:
         raise ValueError('Unsupported dictionary entry type %d' % t)
      return v

   def get_array(self, key):
      "Return a _reference_ to an array stored in this Dictionary"""
      
      import _quippy, arraydata
      if key in self and self.get_type_and_size(key)[0] in Dictionary._array_types:
         return arraydata.get_array(self._fpointer, _quippy.qp_dictionary_get_array, key).view(FortranArray)
      else:
         raise KeyError('Key "%s" does not correspond to an array entry' % key)


   def __getitem__(self, k):
      k = k.lower()

      if self.cache_invalid:
         self._cache = {}
         self.cache_invalid = 0
         
      try:
         v = self._cache[k]
         if v is None: raise KeyError
         return v
      
      except KeyError:
         if not k in self:
            raise KeyError('Key "%s" not found ' % k)

         t = self.get_type_and_size(k)[0]

         if t == T_NONE:
            raise ValueError('Key %s has no associated value' % k)

         elif t in Dictionary._scalar_types:
            self._cache[k] = None
            return self.get_value(k)

         elif t in Dictionary._array_types:
            v = self.get_array(k)
            self._cache[k] = v
            return v

         else:
            raise ValueError('Unsupported dictionary entry type %d' % t)


   def __setitem__(self, k, v):
      try:
         self.set_value(k, v)
      except TypeError:
         self.set_value(k,s2a(v))

   def __delitem__(self, k):
      i = self.lookup_entry_i(k)
      if i == -1:
         raise KeyError('Key %s not found in Dictionary' % k)
      self.remove_entry(i)

   def __repr__(self):
      return ParamReaderMixin.__repr__(self)

   def __eq__(self, other):
      tol = 1e-8
      if sorted(self.keys()) != sorted(other.keys()): return False

      for key in self:
         v1, v2 = self[key], other[key]
         if isinstance(v1, FortranArray) and isinstance(v2, FortranArray):
            if v1.dtype.kind != 'f':
               if (v1 != v2).any(): return False
            else:
               if abs(v1 - v2).max() > tol: return False
         else:
            if v1 != v2: return False
      return True
         
   def __ne__(self, other):
      return not self.__eq__(other)

   def __str__(self):
      return ParamReaderMixin.__str__(self)

   def copy(self):
      return Dictionary(self)

     

class Table(FortranTable):

   __doc__ = FortranTable.__doc__

   def __repr__(self):
      return ('Table(n=%d,intsize=%d,realsize=%d,strsize=%d,logicalsize=%d)' %
              (self.n, self.intsize, self.realsize, self.strsize, self.logicalsize))

   def __str__(self):
      return repr(self)

   def copy(self):
      t = Table(self.intsize, self.realsize, self.strsize, self.logicalsize, self.n)
      t.append(blank_rows=self.n)
      if self.intsize != 0: t.int[...] = self.int[...]
      if self.realsize != 0: t.real[...] = self.real[...]
      if self.strsize != 0: t.str[...] = self.str[...]
      if self.logicalsize != 0: t.logical[...] = self.logical[...]
      return t

   def __eq__(self, other):
      return self.equal(other)

   def __ne__(self, other):
      return not self.equal(other)

   def equal(self, other):
      tol = 1e-8
      
      for t1, t2 in zip((self.n,  self.intsize,  self.realsize,  self.strsize,  self.logicalsize),
                        (other.n, other.intsize, other.realsize, other.strsize, other.logicalsize)):
         if t1 != t2: return False

      for n, a1, a2, in zip((self.intsize, self.realsize, self.strsize, self.logicalsize),
                            (self.int,  self.real,  self.str,  self.logical),
                            (other.int, other.real, other.str, other.logical)):

         if n == 0: continue
         try:
            if abs(a1 - a2).max() > tol: return False
         except TypeError:
            if (a1 != a2).any(): return False

      return True


   def _get_array_shape(self, name):
       if name in ('int','real','logical'):
           return (slice(None),slice(1,self.n))
       elif name == 'str':
           return (slice(None),slice(None),slice(1,self.n))
       else:
          return None


class DynamicalSystem(FortranDynamicalSystem):

   __doc__ = FortranDynamicalSystem.__doc__

   def run(self, pot, dt, n_steps, hook_interval=None, write_interval=None, connect_interval=None, trajectory=None, args_str=None, hook=None,
           save_interval=None):
      if hook is None:
         if hook_interval is not None:
            raise ValueError('hook_interval not permitted when hook is not present. save_interval is used instead')
         traj = []
         FortranDynamicalSystem.run(self, pot, dt, n_steps, hook_interval=save_interval, write_interval=write_interval, 
                                    connect_interval=connect_interval, trajectory=trajectory, args_str=args_str, hook=lambda:traj.append(self.atoms.copy()))
         return traj
      else:
         FortranDynamicalSystem.run(self, pot, dt, n_steps, hook, hook_interval, write_interval, 
                                    connect_interval, trajectory, args_str)

from quippy import INPUT, OUTPUT, INOUT


class CInOutput(FortranCInOutput):

   __doc__ = FortranCInOutput.__doc__

   def __init__(self, filename=None, action=INPUT, append=False, netcdf4=True, zero=False, fpointer=None, finalise=True):
      FortranCInOutput.__init__(self, filename, action, append, netcdf4, fpointer=fpointer, finalise=finalise)
      self.zero = zero

   __init__.__doc__ = FortranCInOutput.__init__.__doc__

   def __len__(self):
      return int(self.n_frame)

   def __getitem__(self, index):
      return self.read(frame=index, zero=self.zero)

   def __setitem__(self, index, value):
      self.write(value, frame=index)

   def write(self, at, properties=None, prefix=None, int_format=None, real_format=None, frame=None,
             shuffle=None, deflate=None, deflate_level=None):

      if properties is not None and (not hasattr(properties, 'dtype') or properties.dtype != dtype('S1')):
         properties = padded_str_array(properties, max([len(x) for x in properties])).T

      FortranCInOutput.write(self, at, properties_array=properties, prefix=prefix, int_format=int_format,
                             real_format=real_format, frame=frame, shuffle=shuffle, deflate=deflate,
                             deflate_level=deflate_level)
                             
class Potential(FortranPotential):

   __doc__ = FortranPotential.__doc__
   callback_map = {}
   
   def __init__(self, args_str, *args, **kwargs):
      if args_str.lower().startswith('callbackpot') and not 'label' in args_str:
         args_str = args_str + ' label=%d' % id(self)
      FortranPotential.__init__(self, args_str, *args, **kwargs)

      if args_str.lower().startswith('callbackpot'):
         FortranPotential.set_callback(self, Potential.callback)

   __init__.__doc__ = FortranPotential.__init__.__doc__

   @staticmethod
   def callback(at_ptr):
      at = Atoms(fpointer=at_ptr, finalise=False)
      if at.params['label'] not in Potential.callback_map:
         raise ValueError('Unknown Callback potential label %s' % at.params['label'])
      Potential.callback_map[at.params['label']](at)

   def set_callback(self, callback):
      Potential.callback_map[str(id(self))] = callback


