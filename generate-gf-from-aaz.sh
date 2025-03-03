#!/bin/bash

modules=("device-registry" "standby-pool" "compute-schedule" "document-db/mongo-cluster" "mdp" "api-center" "apic" "compute-fleet" "dev-ops-infrastructure" "health-data-ai-services" "healthcareapis" "large-storage-instance")
#modules=("device-registry" "standby-pool")
modules=("compute-schedule")

scripts="python ./aaz-dev/diff-aaz-model-from-swagger-tsp.py"
swagger_aaz_base="/Users/allywang/workspace_tsp1/swagger-res/aaz/Commands/"
tsp_aaz_base="/Users/allywang/workspace_tsp1/tsp-res/aaz/Commands/"
# 遍历子目录并执行命令
for moddir in "${modules[@]}"; do
    echo "swagger aaz folder: ${swagger_aaz_base}${moddir}"
    echo "tsp aaz folder: ${tsp_aaz_base}${moddir}"
    if [ -d "${swagger_aaz_base}${moddir}" ] && [ -d "${tsp_aaz_base}${moddir}" ]; then

#        cd "$moddir" || continue
        command="${scripts} --rpas ${swagger_aaz_base}${moddir} --rpat ${tsp_aaz_base}${moddir}"
        echo run ${command}
        ${command}
        if [ $? -ne 0 ]; then
          echo "${moddir} gen aaz model diff failed, pass"
          continue
        else
          echo "${moddir} gen aaz model diff succeed"
        fi
#        cd - || continue
    else
        echo "$moddir under aaz base is not a directory, please check"
    fi
done
