## 文档目录（用 read_reference 读）
这些是 SCA 官方的建模文档，英文。它们是写给直接写模型文件的人看的：其中关于文件结构、var()、打印、导出、打包的要求都由程序负责，你不用管，只取其中的建模方法。
- mechanical-modeling：规划阶段，零件比较复杂、不知道先做什么后做什么、该用拉伸还是旋转时读。
- datums-and-coordinate-systems：不知道原点和基准面该定在哪里时读。
- feature-ordering：拿不准特征的先后顺序时读，比如圆角、抽壳、阵列该放在哪一步，布尔运算的刀具要多长。
- sketch-and-features：要用草图画轮廓，再拉伸、旋转、扫掠或放样时读。
- standard-parts：要做齿轮、齿条、轴承这类标准件时读。标准件一律用现成的函数，不要自己画齿形。
- part-modeling：布尔运算失败，或者合并后出现了多个实体时读。
- ql-playbook：选面、选边的条件写不对，或者要给圆角、倒角选边时读。
- geometric-validation：不知道一条要求该怎么写成检查，或者检查通过了但你怀疑它没测到点子上时读。
- failure-and-repair：同一个错误改了两次还没好时读，按里面的分类找原因。
- manufacturing-boundaries：需要给壁厚、最小孔径、间隙这类尺寸定一个合理的建议值时读。
