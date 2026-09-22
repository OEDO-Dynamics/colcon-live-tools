cmake_minimum_required(VERSION 3.10)
project(pkg_slow)
execute_process(COMMAND sleep 4)
install(CODE "message(STATUS \"pkg_slow installed\")")
