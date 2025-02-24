#!/bin/bash

modules=("astronomer" "liftrbasic" "arize-ai" "lambda-test" "mongo-db" "neon/postgres" "liftr-pilot" "pinecone" "qumulo" "weights-and-biases")

scripts="./aaz-dev/diff-aaz-model-from-swagger-tsp.py"
swagger_aaz_base="C:\Users\liwang3\workspace_tsp\swagger-res\aaz\Commands\"
tsp_aaz_base="C:\Users\liwang3\workspace_tsp\tsp-res\aaz\Commands\"
# 遍历子目录并执行命令
for moddir in "${modules[@]}"; do
    if [ -d "${swagger_aaz_base}${moddir}" && -d "${tsp_aaz_base}${moddir}" ]; then
        echo "swagger aaz folder: ${swagger_aaz_base}${moddir}"
        echo "tsp aaz folder: ${tsp_aaz_base}${moddir}"
#        cd "$moddir" || continue
        command="${scripts} --rpas ${swagger_aaz_base}${moddir} --rpas ${tsp_aaz_base}${moddir}"
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
