from firedrake import *
from forms import *
from tsfc import compile_form
import loopy as lp
import numpy as np
import argparse
from functools import reduce
import operator


parser = argparse.ArgumentParser()
parser.add_argument('--form', dest='form', default="helmholtz", type=str)
parser.add_argument('--p', dest='p', default=1, type=int)
parser.add_argument('--n', dest='n', default=32, type=int)
parser.add_argument('--f', dest='f', default=0, type=int)
parser.add_argument('--repeat', dest='repeat', default=1, type=int)
parser.add_argument('--mesh', dest='m', default="tri", type=str, choices=["quad", "tet", "hex", "tri"])
parser.add_argument('--print', default=False, action="store_true")
args, _ = parser.parse_known_args()

n = args.n
p = args.p
f = args.f
repeat = args.repeat
m = args.m
form_str = args.form

if m == "quad":
    mesh = IntervalMesh(n, n)
    mesh = ExtrudedMesh(mesh, n, layer_height=1.0)
    # mesh = SquareMesh(n, n, L=n, quadrilateral=True)
elif m == "tet":
    mesh = CubeMesh(n, n, n, L=n)
elif m == "hex":
    mesh = SquareMesh(n, n, L=n, quadrilateral=True)
    mesh = ExtrudedMesh(mesh, n, layer_height=1.0)
else:
    assert m == "tri"
    mesh = SquareMesh(n, n, L=n)

if form_str in ["mass", "helmholtz"]:
    V = FunctionSpace(mesh, "CG", p)
elif form_str in ["laplacian", "elasticity", "hyperelasticity", "holzapfel"]:
    V = VectorFunctionSpace(mesh, "CG", p)
else:
    raise AssertionError()

x = Function(V)

xs = SpatialCoordinate(mesh)
if V.ufl_element().value_size() > 1:
    x.interpolate(as_vector(xs))
else:
    x.interpolate(reduce(operator.add, xs))

form = eval(form_str)(p, p, mesh, f)
y_form = action(form, x)

y = Function(V)
for i in range(repeat):
   assemble(y_form, tensor=y)
   y.dat.data

if args.print:
    import pickle
    pickle.dump(y.vector()[:], open("test.obj", "wb"))
    print(y.vector()[:])
    exit(0)

cells = mesh.comm.allreduce(mesh.cell_set.size)
dofs = mesh.comm.allreduce(V.dof_count)
rank = mesh.comm.Get_rank()

if rank == 0:
    if mesh.layers:
        cells = cells * (mesh.layers - 1)
    print("CELLS= {0}".format(cells))
    print("DOFS= {0}".format(dofs))

    from loopy.program import make_program

    knl = compile_form(y_form, coffee=False)[0].ast
    warnings = list(knl.silenced_warnings)
    warnings.extend(["insn_count_subgroups_upper_bound", "no_lid_found"])
    knl = knl.copy(silenced_warnings=warnings)
    knl.options.ignore_boostable_into = True

    program = make_program(knl)
    op_map = lp.get_op_map(program, subgroup_size=1)
    mem_map = lp.get_mem_access_map(program, subgroup_size=1)

    for op in ['add', 'sub', 'mul', 'div']:
        print("{0}S= {1}".format(op.upper(), op_map.filter_by(name=[op], dtype=[np.float64]).eval_and_sum({})))
    print("MEMS= {0}".format(mem_map.filter_by(mtype=['global'], dtype=[np.float64]).eval_and_sum({})))
    print("INSTRUCTIONS= {0:d}".format(len(knl.instructions)))
    print("LOOPS= {0:d}".format(len(knl.all_inames())))
    for domain in knl.domains:
        if domain.get_dim_name(3, 0)[0] == "j":
            print("DOF_LOOP_EXTENT= {0:d}".format(int(domain.dim_max_val(0).to_str()) + 1))
            break
    else:
        print("DOF_LOOP_EXTENT= 1")
    for domain in knl.domains:
        if domain.get_dim_name(3, 0)[0:2] == "ip":
            print("QUADRATURE_LOOP_EXTENT= {0:d}".format(int(domain.dim_max_val(0).to_str()) + 1))
            break
    else:
        print("QUADRATURE_LOOP_EXTENT= 1")
