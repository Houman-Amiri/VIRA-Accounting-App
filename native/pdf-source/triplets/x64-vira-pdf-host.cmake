# Build-only tools use a shared dynamic CRT (gettext passes CRT-owned state).
# No host DLL or executable is copied into the private runtime candidate.
set(VCPKG_TARGET_ARCHITECTURE x64)
set(VCPKG_CRT_LINKAGE dynamic)
set(VCPKG_LIBRARY_LINKAGE dynamic)
set(VCPKG_BUILD_TYPE release)
