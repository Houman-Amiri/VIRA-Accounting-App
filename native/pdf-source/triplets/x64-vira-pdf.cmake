# Private source-build experiment: replaceable DLLs, no assumed MSVC redist.
# Static CRT support and the resulting PE closure must be verified, not assumed.
set(VCPKG_TARGET_ARCHITECTURE x64)
set(VCPKG_CRT_LINKAGE static)
set(VCPKG_LIBRARY_LINKAGE dynamic)
set(VCPKG_BUILD_TYPE release)
