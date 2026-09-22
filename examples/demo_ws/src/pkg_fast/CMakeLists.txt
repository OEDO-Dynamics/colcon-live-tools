cmake_minimum_required(VERSION 3.10)
project(pkg_fast)
execute_process(COMMAND sleep 1)
install(CODE "message(STATUS \"pkg_fast installed\")")
