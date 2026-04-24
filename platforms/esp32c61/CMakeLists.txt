cmake_minimum_required(VERSION 3.16)

set(ALGO_SELECTED "ascon_aead128" CACHE STRING "ORBIT algorithm to build")
set(ORBIT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../.." CACHE PATH "ORBIT repository root")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(ORBIT_${ALGO_SELECTED}_esp32c61)
