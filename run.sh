rm mass_small/mat/*
rm mass_small/Model/*
rm mass_small/result_img/*
rm mass_small_4_param/mat/*
rm mass_small_4_param/Model/*
rm mass_small_4_param/result_img/*
cd mass_small
python deepGW_train_multi_gpu.py
python deepGW_test_multi_gpu.py
cd ..
cd mass_small_4_param
python deepGW_train_multi_gpu.py
python deepGW_test_multi_gpu.py