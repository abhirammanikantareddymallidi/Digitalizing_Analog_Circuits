"""
Physical constants used throughout the framework.
All values in SI units unless otherwise noted.
"""

import math

PHYSICAL_CONSTANTS = {
    # Fundamental constants
    "q": 1.602176634e-19,           # Elementary charge (C)
    "k_B": 1.380649e-23,            # Boltzmann constant (J/K)
    "epsilon_0": 8.854187817e-12,   # Vacuum permittivity (F/m)
    "epsilon_si": 11.7,             # Relative permittivity of silicon
    "epsilon_ox": 3.9,              # Relative permittivity of SiO2
    "h": 6.62607015e-34,            # Planck constant (J·s)
    "c": 299792458.0,               # Speed of light (m/s)
    "m_e": 9.1093837015e-31,        # Electron mass (kg)
    "T_room": 300.0,                # Room temperature (K)
    "V_T_room": 0.02585,            # Thermal voltage at 300 K (V)

    # Silicon material properties
    "E_g_si": 1.12,                 # Silicon bandgap at 300 K (eV)
    "n_i_si": 1.5e10,              # Intrinsic carrier concentration (cm⁻³)
    "mu_n_si": 600e-4,             # Electron mobility in Si (m²/V·s) ≈ 600 cm²/V·s
    "mu_p_si": 250e-4,             # Hole mobility in Si (m²/V·s) ≈ 250 cm²/V·s

    # Typical CMOS process parameters (generic 180nm-like)
    "t_ox_typical": 4e-9,          # Gate oxide thickness (m)
    "Cox_typical": 8.63e-3,        # Oxide capacitance (F/m²) for 4nm tox
    "VTH_n_typical": 0.4,          # Typical NMOS threshold voltage (V)
    "VTH_p_typical": -0.4,         # Typical PMOS threshold voltage (V)
    "lambda_n_typical": 0.1,       # NMOS channel-length modulation (V⁻¹)
    "lambda_p_typical": 0.2,       # PMOS channel-length modulation (V⁻¹)
    "mu_n_typical": 450e-4,        # Typical NMOS mobility (m²/V·s)
    "mu_p_typical": 120e-4,        # Typical PMOS mobility (m²/V·s)
    "VDD_typical": 1.8,            # Typical supply voltage (V)
}


def thermal_voltage(T=300.0):
    """Calculate thermal voltage V_T = k_B * T / q."""
    return PHYSICAL_CONSTANTS["k_B"] * T / PHYSICAL_CONSTANTS["q"]


def oxide_capacitance(t_ox, epsilon_ox=3.9):
    """Calculate gate oxide capacitance per unit area: Cox = epsilon_0 * epsilon_ox / t_ox."""
    return PHYSICAL_CONSTANTS["epsilon_0"] * epsilon_ox / t_ox


def intrinsic_carrier_concentration(T=300.0):
    """
    Approximate intrinsic carrier concentration for silicon.
    n_i ≈ 5.29e19 * (T/300)^2.54 * exp(-6726/T)  cm⁻³
    """
    return 5.29e19 * (T / 300.0) ** 2.54 * math.exp(-6726.0 / T)
