@echo off
setlocal enabledelayedexpansion

set modules=astronomer liftrbasic arize-ai lambda-test mongo-db neon/postgres liftr-pilot pinecone qumulo weights-and-biases

set scripts=.\aaz-dev\diff-aaz-model-from-swagger-tsp.py

set swagger_aaz_base=C:\Users\liwang3\workspace_tsp\swagger-res\aaz\Commands\
set tsp_aaz_base=C:\Users\liwang3\workspace_tsp\tsp-res\aaz\Commands\

for %%m in (%modules%) do (
    set swagger_aaz_dir=%swagger_aaz_base%%%m
    set tsp_aaz_dir=%tsp_aaz_base%%%m

    if exist "!swagger_aaz_dir!" if exist "!tsp_aaz_dir!" (
        echo swagger aaz folder: !swagger_aaz_dir!
        echo tsp aaz folder: !tsp_aaz_dir!

        set command=python %scripts% --rpas !swagger_aaz_dir! --rpas !tsp_aaz_dir!
        echo Run: !command!
        call !command!

        :: 检查命令是否成功执行
        if !errorlevel! neq 0 (
            echo %%m gen aaz model diff failed, pass
        ) else (
            echo %%m gen aaz model diff succeed
        )
    ) else (
        echo %%m under aaz base is not a directory, please check
    )
)

endlocal
pause
