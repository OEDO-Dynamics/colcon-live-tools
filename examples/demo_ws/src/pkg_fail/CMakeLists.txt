cmake_minimum_required(VERSION 3.10)
project(pkg_fail)
execute_process(COMMAND sleep 1)
message(FATAL_ERROR "intentional failure in pkg_fail, for demoing the failure report")
