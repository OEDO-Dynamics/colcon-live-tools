cmake_minimum_required(VERSION 3.10)
project(pkg_mid)
execute_process(COMMAND sleep 2)
install(CODE "message(STATUS \"pkg_mid installed\")")
