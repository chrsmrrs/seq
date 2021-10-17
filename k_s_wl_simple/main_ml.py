import itertools
from itertools import product, combinations, combinations_with_replacement

import numpy as np
from graph_tool.all import *
from data_set_parser import read_txt, get_dataset
from svm import linear_svm_evaluation, kernel_svm_evaluation
from aux import normalize_gram_matrix, normalize_feature_vector
from scipy import sparse as sp

import graph_generator as gen
import time


# Compute atomic type for ordered set of vertices of graph g.
def compute_atomic_type(g, vertices, node_label):
    edge_list = []

    # Loop over all pairs of vertices.
    for i, v in enumerate(vertices):
        for j, w in enumerate(vertices):
            # Check if edge or self loop.
            if g.edge(v, w):
                if node_label:
                    edge_list.append((i, j, 1, g.vp.nl[v], g.vp.nl[w]))
                else:
                    edge_list.append((i, j, 1))
            elif not g.edge(v, w):
                if node_label:
                    edge_list.append((i, j, 2, g.vp.nl[v], g.vp.nl[w]))
                else:
                    edge_list.append((i, j, 2))
            elif v == w:
                if node_label:
                    edge_list.append((i, j, 3, g.vp.nl[v], g.vp.nl[w]))
                else:
                    edge_list.append((i, j, 3))

    edge_list.sort()

    return hash(tuple(edge_list))


# Naive implementation of the (k,s)-WL.
def compute_k_s_tuple_graph(graphs, k, s, node_label):
    tupled_graphs = []
    node_labels_all = []
    edge_labels_all = []

    # Manage atomic types.
    atomic_type = {}
    atomic_counter = 0

    degrees = []

    for g in graphs:
        # k-tuple graph.
        k_tuple_graph = Graph(directed=False)

        # Create iterator over all k-tuples of the graph g.
        tuples = product(g.vertices(), repeat=k)

        # Map from tuple back to node in k-tuple graph.
        tuple_to_node = {}
        # Inverse of above.
        node_to_tuple = {}

        # Manages node_labels, i.e., atomic types.
        node_labels = k_tuple_graph.new_vertex_property("int")
        # True if tuples exsits in k-tuple graph.
        tuple_exists = {}

        # Create nodes for k-tuples.
        for c, t in enumerate(tuples):

            # Ordered set of nodes of tuple t.
            node_set = list(t)

            # Create graph induced by tuple t.
            vfilt = g.new_vertex_property('bool')
            for v in t:
                vfilt[v] = True
            k_graph = GraphView(g, vfilt)

            # Compute number of components.
            components, _ = graph_tool.topology.label_components(k_graph)
            num_components = components.a.max() + 1

            # Check if tuple t induces less than s+1 components.
            if num_components <= s:
                tuple_exists[t] = True
            else:
                tuple_exists[t] = False
                # Skip tuple.
                continue

            # Add vertex to k-tuple graph representing tuple t.
            v = k_tuple_graph.add_vertex()

            # Compute atomic type.
            raw_type = compute_atomic_type(g, node_set, node_label)

            # Atomic type seen before.
            if raw_type in atomic_type:
                node_labels[v] = atomic_type[raw_type]
            else:  # Atomic type not seen before.
                node_labels[v] = atomic_counter
                atomic_type[raw_type] = atomic_counter
                atomic_counter += 1

            # Manage mappings, back and forth.
            node_to_tuple[v] = t
            tuple_to_node[t] = v

        # Iterate over nodes and add edges.
        edge_labels = k_tuple_graph.new_edge_property("int")

        for c, m in enumerate(k_tuple_graph.vertices()):

            # Get corresponding tuple.
            t = list(node_to_tuple[m])

            # Iterate over components of t.
            for i in range(0, k):
                # Node to be exchanged.
                v = t[i]

                # Iterate over neighbors of node v in the original graph.
                for ex in v.out_neighbors():
                    # Copy tuple t.
                    n = t[:]

                    # Exchange node v by node ex in n (i.e., t).
                    n[i] = ex

                    # Check if tuple exists, otherwise ignore.
                    if tuple_exists[tuple(n)]:
                        w = tuple_to_node[tuple(n)]

                        # Insert edge, avoid undirected multi-edges.
                        if not k_tuple_graph.edge(w, m):
                            k_tuple_graph.add_edge(m, w)
                            edge_labels[(m, w)] = 1 #i + 1
                            edge_labels[(w, m)] = 1 #i + 1

            # Add self-loops, only once.
            k_tuple_graph.add_edge(m, m)
            edge_labels[(m, m)] = 0

        k_tuple_graph.vp.node_labels = node_labels
        tupled_graphs.append(k_tuple_graph)

    return tupled_graphs






# Implementation of the (k,s)-WL.
def compute_k_s_tuple_graph_fast(graphs, k, s, node_label):
    tupled_graphs = []
    node_labels_all = []
    edge_labels_all = []

    # Manage atomic types.
    atomic_type = {}
    atomic_counter = 0

    for y,g in enumerate(graphs):
        # (k,s)-tuple graph.
        k_tuple_graph = Graph(directed=False)

        # Map from tuple back to node in k-tuple graph.
        tuple_to_node = {}
        # Inverse of above.
        node_to_tuple = {}

        # Manages node_labels, i.e., atomic types.
        node_labels = {}
        # True if tuple exists in k-tuple graph.
        tuple_exists = {}
        # True if connected multi-set has been found already.
        multiset_exists = {}

        # List of s-multisets.
        k_multisets = combinations_with_replacement(g.vertices(), r = s)

        # Generate (k,s)-multisets.
        for _ in range(s, k):
            # Contains (k,s)-multisets extended by one vertex.
            ext_multisets = []
            # Iterate over every multiset.
            for ms in k_multisets:
                # Iterate over every element in multiset.
                for v in ms:
                    # Iterate over neighbors.
                    for w in v.out_neighbors():
                        # Extend multiset by neighbor w.
                        new_multiset = list(ms[:])
                        new_multiset.append(w)
                        new_multiset.sort()

                        # Check if set already exits to avoid duplicates.
                        if not (tuple(new_multiset) in multiset_exists):
                            multiset_exists[tuple(new_multiset)] = True
                            ext_multisets.append(list(new_multiset[:]))

                    # Self-loop.
                    new_multiset = list(ms[:])
                    new_multiset.append(v)
                    new_multiset.sort()

                    # Check if set already exits to avoid duplicates.
                    if not (tuple(new_multiset) in multiset_exists):
                        multiset_exists[tuple(new_multiset)] = True
                        ext_multisets.append(new_multiset)

            k_multisets = ext_multisets

        if k == s:
            k_multisets = list(k_multisets)
            #print(len(k_multisets))

        # Generate nodes of (k,s)-graph.
        # Iterate of (k,s)-multisets.
        for ms in k_multisets:
            # Create all permutations of multiset.
            permutations = itertools.permutations(ms)

            # Iterate over permutations of multiset.
            for t in permutations:
                # Check if tuple t aready exists. # TODO: Needed?
                if t not in tuple_exists:
                    tuple_exists[t] = True

                    # Add vertex to k-tuple graph representing tuple t.
                    t_v = k_tuple_graph.add_vertex()

                    # Compute atomic type.
                    raw_type = compute_atomic_type(g, t, node_label)

                    # Atomic type seen before.
                    if raw_type in atomic_type:
                        node_labels[t_v] = atomic_type[raw_type]
                    else:  # Atomic type not seen before.
                        node_labels[t_v] = atomic_counter
                        atomic_type[raw_type] = atomic_counter
                        atomic_counter += 1

                    # Manage mappings, back and forth.
                    node_to_tuple[t_v] = t
                    tuple_to_node[t] = t_v

        # Iterate over nodes and add edges.
        edge_labels = {}
        for c, m in enumerate(k_tuple_graph.vertices()):

            # Get corresponding tuple.
            t = list(node_to_tuple[m])

            # Iterate over components of t.
            for i in range(0, k):
                # Node to be exchanged.
                v = t[i]

                # Iterate over neighbors of node v in the original graph.
                for ex in v.out_neighbors():
                    # Copy tuple t.
                    n = t[:]

                    # Exchange node v by node ex in n (i.e., t).
                    n[i] = ex

                    # Check if tuple exists, otherwise ignore.
                    if tuple(n) in tuple_exists:
                        w = tuple_to_node[tuple(n)]

                        # Insert edge, avoid undirected multi-edges.
                        if not k_tuple_graph.edge(w, m):
                            k_tuple_graph.add_edge(m, w)
                            edge_labels[(m, w)] = i + 1
                            edge_labels[(w, m)] = i + 1

            # Add self-loops, only once.
            k_tuple_graph.add_edge(m, m)
            edge_labels[(m, m)] = 0

        tupled_graphs.append(k_tuple_graph)
        node_labels_all.append(node_labels)
        edge_labels_all.append(edge_labels)

    return tupled_graphs, node_labels_all, edge_labels_all


# Simple implementation of 1-WL for edge and node-labeled graphs.
def compute_wl(graph_db, node_labels, edge_labels, num_it):
    # Create one empty feature vector for each graph.
    feature_vectors = []
    for _ in graph_db:
        feature_vectors.append(np.zeros(0, dtype=np.float64))

    offset = 0
    graph_indices = []

    for g in graph_db:
        graph_indices.append((offset, offset + g.num_vertices() - 1))
        offset += g.num_vertices()

    colors = []
    for i, g in enumerate(graph_db):
        for v in g.vertices():
            colors.append(node_labels[i][v])

    max_all = int(np.amax(colors) + 1)
    feature_vectors = [
        np.concatenate((feature_vectors[i], np.bincount(colors[index[0]:index[1] + 1], minlength=max_all))) for
        i, index in enumerate(graph_indices)]

    dim = feature_vectors[0].shape[-1]

    c = 0
    #while True:
    while c <= num_it:
        colors = []

        for i, g in enumerate(graph_db):
            for v in g.vertices():
                neighbors = []

                out_edges_v = g.get_out_edges(v).tolist()
                for (_, w) in out_edges_v:
                    neighbors.append(hash((node_labels[i][w], edge_labels[i][(v, w)])))

                neighbors.sort()
                neighbors.append(node_labels[i][v])
                colors.append(hash(tuple(neighbors)))

        _, colors = np.unique(colors, return_inverse=True)

        # Assign new colors to vertices.
        q = 0
        for i, g in enumerate(graph_db):
            for v in g.vertices():
                node_labels[i][v] = colors[q]
                q += 1

        max_all = int(np.amax(colors) + 1)

        feature_vectors = [np.bincount(colors[index[0]:index[1] + 1], minlength=max_all) for i, index in
                           enumerate(graph_indices)]

        dim_new = feature_vectors[0].shape[-1]

        # if dim_new == dim:
        #     break
        dim = dim_new

        c += 1

    #print(c)

    feature_vectors = np.array(feature_vectors)
    gram_matrix = np.dot(feature_vectors, feature_vectors.transpose())

    return gram_matrix


name = "ENZYMES"
_ = get_dataset(name)
graphs, classes = read_txt(name)
tupled_graphs, node_labels, edge_labels = compute_k_s_tuple_graph(graphs, k=2, s=1, node_label=True)
kernel = compute_wl(tupled_graphs, node_labels, edge_labels, num_it=4)
kernel = normalize_gram_matrix(kernel)


print(linear_svm_evaluation([kernel], classes))
