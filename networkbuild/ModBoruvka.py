import heapq
import numpy as np
import networkx as nx 
import pandas as pd

from copy import copy
from numba import jit
from rtree import index
from scipy.spatial import cKDTree

class Dict(dict):
    """dictionary allowing weakref"""
    pass

def memoize(f):
    """ Memoization decorator for a function taking one or more arguments. """
    class memodict(dict):
        def __getitem__(self, *key):
            return dict.__getitem__(self, key)

        def __missing__(self, key):
            ret = self[key] = f(*key)
            return ret

class UnionFind:
    """Union-find data structure.

    Each unionFind instance X maintains a family of disjoint sets of
    hashable objects, supporting the following two methods:

    - X[item] returns a name for the set containing the given item.
      Each set is named by an arbitrarily-chosen one of its members; as
      long as the set remains unchanged it will keep the same name. If
      the item is not yet part of a set in X, a new singleton set is
      created for it.

    - X.union(item1, item2, ...) merges the sets containing each item
      into a single larger set.  If any item is not yet part of a set
      in X, it is added to X as one of the members of the merged set.

      Union-find data structure. Based on Josiah Carlson's code,
      http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/215912
      with significant additional changes by D. Eppstein.
      http://www.ics.uci.edu/~eppstein/PADS/UnionFind.py

    """

    def __init__(self, G):
        """Create a new empty union-find structure."""
        self.graph = G 
        self.weights = {}
        self.mv = {}
        self.parents = {}
        self.children = Dict()
        self.queues = {}
    
    def __getitem__(self, object):
        """Find and return the name of the set containing the object."""

        # check for previously unknown object
        if object not in self.parents:
            self.parents[object] = object
            self.weights[object] = 1
            self.mv[object] = self.graph.node[object]['mv']
            self.children[object] = [object]
            self.queues[object] = PriorityQueue()
            return object

        # find path of objects leading to the root
        path = [object]
        root = self.parents[object]
        while root != path[-1]:
            path.append(root)
            root = self.parents[root]

        # compress the path and return
        for ancestor in path:
            self.parents[ancestor] = root
        return root
        
    def __iter__(self):
        """Iterate through all items ever found or unioned by this structure."""
        return iter(self.parents)

    def union(self, g1, g2, d):
        """Find the sets containing the objects and merge them all."""
        roots = [self[x] for x in [g1, g2]]
        heaviest = max([(self.weights[r],r) for r in roots])[1]
        r = [r for r in roots if r != heaviest][0]
        
        self.parents[r] = heaviest
        self.weights[heaviest] += self.weights[r]
        
        self.mv[heaviest] = (self.mv[g1] + self.mv[g2]) - d
        self.mv[r] = self.mv[heaviest]
        
        self.children[heaviest] += self.children[r]
        self.children[r] = self.children[heaviest]
    
        self.queues[heaviest].merge(self.queues[r])
        self.queues[r] = self.queues[heaviest] 
    
    def connected_components(self):
        """Return the roots for all disjoint sets"""
        return set([self[r] for r in self.parents.keys()])
    
    def component_set(self, r):
        """return the component set of the objects"""
        
        return self.children[self[r]]

class PriorityQueue:
    def __init__(self):
        self._queue = []
        self._index = 0

    def push(self, item, priority):
        heapq.heappush(self._queue, (priority, self._index, item))
        self._index += 1

    def pop(self):
        return heapq.heappop(self._queue)[-1]
    
    def merge(self, other):
        while other._queue:
            priority,i,item = heapq.heappop(other._queue)
            self.push(item, priority)
        self._queue = list(set(self._queue))
        
    def top(self):
        try:
            return self._queue[0][-1]
        except:
            return None

@jit
def sq_dist(a,b):
    """
    calculates square distance to reduce performance overhead of sqrt
    """
    return np.sum((a-b)**2)

def hav_dist(point1, point2):
    x1, y1 = point1
    x2, y2 = point2
    return get_hav_distance(y1, x1, y2, x2)

@memoize
def get_hav_distance(lat, lon, pcode_lat, pcode_lon):
    """
    Find the distance between a vector of (lat,lon) and the reference point (pcode_lat,pcode_lon).
    """
    rad_factor = pi / 180.0  # degrees to radians for trig functions
    lat_in_rad = lat * rad_factor
    lon_in_rad = lon * rad_factor
    pcode_lat_in_rad = pcode_lat * rad_factor
    pcode_lon_in_rad = pcode_lon * rad_factor
    delta_lon = lon_in_rad - pcode_lon_in_rad
    delta_lat = lat_in_rad - pcode_lat_in_rad
    # Next two lines is the Haversine formula
    inverse_angle = (np.sin(delta_lat / 2) ** 2 + np.cos(pcode_lat_in_rad) *
                     np.cos(lat_in_rad) * np.sin(delta_lon / 2) ** 2)
    haversine_angle = 2 * np.arcsin(np.sqrt(inverse_angle))
    earth_radius =  6371010 # meters
    return haversine_angle * earth_radius

def FNNd(kdtree, A, b):
    """
    kdtree -> nodes in subnet -> coord of b -> index of a
    returns nearest foreign neighbor a∈A of b
    """
    a = None
    b = cartesian_projection(b)
    k = k_cache[str(b)] if str(b) in k_cache else 2
    
    while a not in A:
        _, nn = kdtree.query(b, k=k)
        a = nn[-1][k-1]
        k += 1
    
    k_cache[str(b)] = k-1
    #return NN a ∈ A of b 
    return a

@jit
def cartesian_projection(coords):
    """projects x, y (lon, lat) coordinate pairs to 3D cartesian space"""
    R = 6378137
    
    lon, lat = np.transpose(coords)
    cosLat = np.cos(lat * np.pi / 180.0)
    sinLat = np.sin(lat * np.pi / 180.0)
    cosLon = np.cos(lon * np.pi / 180.0)
    sinLon = np.sin(lon * np.pi / 180.0)
    rad = R
    x = rad * cosLat * cosLon
    y = rad * cosLat * sinLon
    z = rad * sinLat
    return np.column_stack((x,y,z))

def projected_KDTree(coords):
    return cKDTree(cartesian_projection(coords))

@jit
def make_bounding_box(u, v):
    stack = np.row_stack((u, v))
    xmin, xmax = np.argsort(stack[:, 0])
    ymin, ymax = np.argsort(stack[:, 1])
    return stack[xmin][0], stack[ymin][1], stack[xmax][0], stack[ymax][1]

@jit
def line_intersection(rtree, um, vm, coords):
    p1, p2 = coords[um], coords[vm]
    box = make_bounding_box(p1, p2)
    
    # query for overlapping rectangles
    intersecting_bounds = rtree.intersection(box, objects=True)
    
    # go through the possible intersections for to validate
    for possible in intersecting_bounds:
        
        #convert edge from (n , n) -> (coord, coord)
        up, vp = possible.object
        p3, p4 = coords[up], coords[vp]
        
        """
        test for line segment intersection
        http://stackoverflow.com/questions/563198/how-do-you-detect-where-two-line-segments-intersect
        """ 
        r = p2 - p1
        s = p4 - p3
        numerator = np.cross((p3 - p1), r)
        denominator = np.cross(r, s)
        
        if numerator == 0 and denominator == 0:
            # lines are colinear, test if overlapping 
            overlapping = (((p3[0]-p1[0]) < 0) != ((p3[0]-p2[0]) < 0)  != (
                            (p4[0]-p1[0]) < 0) != ((p4[0]-p2[0]) < 0)) or ((
                            (p3[1]-p1[1]) < 0) != ((p3[1]-p2[1]) < 0)  != (
                            (p4[1]-p1[1]) < 0) != ((p4[1] - p2[1]) < 0))
            if overlapping:
                # allow intersection if lines share an endpoint
                if (np.array_equal(p1, p3) and not np.array_equal(p2, p4)) or (
                    np.array_equal(p1, p4) and not np.array_equal(p2, p3)) or (
                    np.array_equal(p2, p3) and not np.array_equal(p1, p4)) or (
                    np.array_equal(p2, p4) and not np.array_equal(p1, p3)):
                    continue
                return True
            else: continue
            
        if denominator == 0:
            # lines are parallel
            continue
            
        u = numerator / denominator
        t = np.cross((p3 - p1), s) / denominator
        
        intersecting = (0 <= t <= 1) and (0 <= u <= 1)
        if intersecting:
            # allow intersection if lines share an endpoint
            if (np.array_equal(p1, p3) and not np.array_equal(p2, p4)) or (
                np.array_equal(p1, p4) and not np.array_equal(p2, p3)) or (
                np.array_equal(p2, p3) and not np.array_equal(p1, p4)) or (
                np.array_equal(p2, p4) and not np.array_equal(p1, p3)):
                continue
                
            #print p1, p2, 'intersects', p3, p4
            return True
            
        
    return False

def modBoruvka(T):
    V = T.nodes(data=False)
    coords = np.row_stack(nx.get_node_attributes(T, 'coords').values())
    kdtree = projected_KDTree(coords)
    rtree = index.Index()
    subgraphs = UnionFind(T)# modified to handle queues, children, mv
    
    #                ∀ v∈V 
    # find the nearest neighbor for all nodes, 
    # initialize a singleton subgraph and populate
    # its a queue with the nn edge where dist is priority
    for v in V:
        vm = FNNd(kdtree, V, coords[v]) 
        dm = sq_dist(coords[v], coords[vm])
        
        root = subgraphs[v]
    
        subgraphs.queues[root].push((v,vm), dm)
        
    Et = [] # Initialize MST edges to empty list 
    
    # MST is complete when there are N-1 edges
    while len(Et) < len(V) - 1: #this criteria may need modified 
        # This is an itermediary list of edges that might be added to the MST
        Ep = PriorityQueue()
        #∀ C of T; where C <- connected component
        for C in subgraphs.connected_components():
            
            q_top = subgraphs.queues[C].top()
            try:
                # MV criteria requires pruning of edges, 
                # meaning this priority queue can empty
                (v, vm) = q_top
            except:
                continue
                
            component_set = subgraphs.component_set(v)
            djointVC = list(set(V) - set(component_set))
            
            # vm ∈ C {not a foreign nearest neighbor}
            # go through the queue until a edge is found that connects two subgraphs
            # while in the loop update the items in the queue, 
            # preventing edges between nodes in the same subgraph
            while vm in component_set:
                subgraphs.queues[C].pop()
                um = FNNd(kdtree, djointVC, coords[v])
                dm = sq_dist(coords[v], coords[um])
                subgraphs.queues[C].push((v,um), dm)
                (v,vm) = subgraphs.queues[C].top()
            
            # use haversine distance when moving into E', as needed for mv criteria
            dm = hav_dist(coords[v], coords[vm])
            # Append the top priority edge from the subgraph to the intermediary edgelist
            Ep.push((v, vm, dm), dm)
            
        # add all the edges in E' to Et so long as no cycles are created
        state = copy(Et)
        while Ep._queue:
            (um, vm, dm) = Ep.pop()

            # if doesn't create cycle and subgraph has enough MV
            if subgraphs[um] != subgraphs[vm] and subgraphs.mv[um] >= dm: 
                # test that the connecting subgraph can receive the MV
                if subgraphs.mv[vm] >= dm:
                    # both two way tests passed
                    subgraphs.union(um, vm, dm)
                    # doesn't create line segment intersection
                    if not line_intersection(rtree, um, vm, coords):
                        rtree.insert(hash((um, vm)), 
                                     make_bounding_box(coords[um], coords[vm]), 
                                     obj=(um, vm))
                        Et += [(um, vm)] 
                        
            else:
                # This edge subgraph will never be able to connect
                # No reason to test this edge further
                try:
                    subgraphs.queues[um].pop()
                except:
                    pass
       
        if Et == state:
            break
    
    T.remove_edges_from(T.edges())
    T.add_edges_from(Et)
    return T