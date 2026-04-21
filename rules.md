# python 环境
conda activate py312

# 数据源  
行情离线数据，使用 pytdx 读取 `C:/new_tdx/vipdoc/sh`、`C:/new_tdx/vipdoc/sz`、`C:/new_tdx/vipdoc/bj` 对应的离线数据  
行情实时数据，使用 opentdx 获取
其余数据，先查看 opentdx 是否提供，若提供，则可以进行读取
> 离线数据是不复权数据，复权因子可通过 opentdx 的 stock_adjust_factor_by_xdxr 获取

# 实时数据
使用 opentdx 获取（但一般不需要）

# 编码规范
现代 python 编码规范，结构化 