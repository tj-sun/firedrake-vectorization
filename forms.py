from firedrake import *
from functools import reduce


def mass(p, q, mesh, nf=0):
    V = FunctionSpace(mesh, 'CG', p)
    P = FunctionSpace(mesh, 'CG', q)
    u = TrialFunction(V)
    v = TestFunction(V)
    it = dot(v, u)
    f = [Function(P).assign(1.0) for _ in range(nf)]
    return reduce(inner, f + [it])*dx


def helmholtz(p, q, mesh, nf=0):
    V = FunctionSpace(mesh, "CG", p)
    P = FunctionSpace(mesh, "CG", q)
    u = TrialFunction(V)
    v = TestFunction(V)
    f = [Function(P).assign(1.0) for _ in range(nf)]
    it = dot(grad(v), grad(u)) + 1.0*v*u
    return reduce(inner, f + [it])*dx


def poissonS(p, q, mesh, nf=0):
    V = FunctionSpace(mesh, "CG", p)
    P = FunctionSpace(mesh, "CG", q)
    u = TrialFunction(V)
    v = TestFunction(V)
    f = [Function(P).assign(1.0) for _ in range(nf)]
    it = dot(grad(v), grad(u))
    return reduce(inner, f + [it])*dx


def elasticity(p, q, mesh, nf=0):
    V = VectorFunctionSpace(mesh, 'CG', p)
    P = FunctionSpace(mesh, 'CG', q)
    u = TrialFunction(V)
    v = TestFunction(V)
    eps = lambda v: grad(v) + transpose(grad(v))
    it = 0.25*inner(eps(v), eps(u))
    f = [Function(P).assign(1.0) for _ in range(nf)]
    return reduce(inner, f + [it])*dx


def hyperelasticity(p, q, mesh, nf=0):
    V = VectorFunctionSpace(mesh, 'CG', p)
    P = VectorFunctionSpace(mesh, 'CG', q)
    v = TestFunction(V)
    du = TrialFunction(V)  # Incremental displacement
    u = Function(V)        # Displacement from previous iteration
    B = Function(V)        # Body force per unit mass
    # Kinematics
    I = Identity(mesh.topological_dimension())
    F = I + grad(u)        # Deformation gradient
    C = F.T*F              # Right Cauchy-Green tensor
    E = (C - I)/2          # Euler-Lagrange strain tensor
    E = variable(E)
    # Material constants
    mu = Constant(1.0)     # Lame's constants
    lmbda = Constant(0.001)
    # Strain energy function (material model)
    psi = lmbda/2*(tr(E)**2) + mu*tr(E*E)
    S = diff(psi, E)       # Second Piola-Kirchhoff stress tensor
    PK = F*S               # First Piola-Kirchoff stress tensor
    # Variational problem
    it = inner(PK, grad(v)) - inner(B, v)
    f = [Function(P).assign(1.0) for _ in range(nf)]
    return derivative(reduce(inner, list(map(div, f)) + [it])*dx, u, du)


def laplacian(p, q, mesh, nf=0):
    V = VectorFunctionSpace(mesh, 'CG', p)
    P = VectorFunctionSpace(mesh, 'CG', q)
    u = TrialFunction(V)
    v = TestFunction(V)
    it = inner(grad(v), grad(u))
    f = [div(Function(P).assign(1.0)) for _ in range(nf)]
    return reduce(inner, f + [it])*dx


def mixed_poisson(p, q, mesh, nf=0):
    BDM = FunctionSpace(mesh, "BDM", p)
    DG = FunctionSpace(mesh, "DG", p - 1)
    P = FunctionSpace(mesh, 'CG', q)
    W = BDM * DG
    sigma, u = TrialFunctions(W)
    tau, v = TestFunctions(W)
    it = dot(sigma, tau) + div(tau)*u + div(sigma)*v
    f = [Function(P).assign(1.0) for _ in range(nf)]
    return reduce(inner, f + [it])*dx

def holzapfel(p, q, mesh, nf=0):
    assert nf == 0

    lamda = Constant(1000.)
    a = Constant(0.5)
    b = Constant(15.0)
    a_s = Constant(21.0)
    b_s = Constant(15.0)
    a_f = Constant(21.0)
    b_f = Constant(11.0)
    a_fs = Constant(20.0)
    b_fs = Constant(10.0)

    # For more fun, make these general vector fields rather than
    # constants:
    e_s = Constant([0.0, 1.0, 0.0])
    e_f = Constant([1.0, 0.0, 0.0])

    # Define the isochoric energy contribution
    def isochoric(F):
        C = F.T * F

        I_1 = tr(C)
        I4_f = dot(e_f, C * e_f)
        I4_s = dot(e_s, C * e_s)
        I8_fs = dot(e_f, C * e_s)

        def cutoff(x):
            return 1.0 / (1.0 + exp(-(x - 1.0) * 30.0))

        def scaled_exp(a0, a1, argument):
            return a0 / (2.0 * a1) * (exp(b * argument) - 1)

        E_1 = scaled_exp(a, b, I_1 - 3.)

        E_f = cutoff(I4_f) * scaled_exp(a_f, b_f, (I4_f - 1.) ** 2)
        E_s = cutoff(I4_s) * scaled_exp(a_s, b_s, (I4_s - 1.) ** 2)
        E_3 = scaled_exp(a_fs, b_fs, I8_fs ** 2)

        E = E_1 + E_f + E_s + E_3
        return E

    # Define mesh and function space
    # mesh = UnitCubeMesh(16, 16, 16)
    V = VectorFunctionSpace(mesh, "CG", p)
    P = VectorFunctionSpace(mesh, 'CG', q)

    u = Function(V)
    v = TestFunction(V)

    # Misc elasticity related tensors and other quantities
    I = Identity(mesh.ufl_cell().topological_dimension())
    F = grad(u) + I
    F = variable(F)
    J = det(F)
    Fbar = J ** (-1.0 / 3.0) * F

    # Define energy
    E_volumetric = lamda * 0.5 * ln(J) ** 2
    psi = isochoric(Fbar) + E_volumetric

    # Find first Piola-Kircchoff tensor
    P = diff(psi, F)

    # Define the variational formulation
    F = inner(P, grad(v)) * dx

    # Take the derivative
    a = derivative(F, u)

    return a
    #
    # f = [Function(P).assign(1.0) for _ in range(nf)]
    # return derivative(reduce(inner, iter + list(map(div, f)))*dx, u)
