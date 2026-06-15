#ns="1 4"
#ns="4"
ns="1"

for n in $ns; do
    echo "starting n=$n"

    l1is="l1i.n.v1..json"
    #l1is="l1i.n.vcs..json"
    #l1is="l1i.n.v1.prefetcher--eip.json"
    #l1is="l1i.n.v1.prefetcher--eip+lower_level--LLC.json"
    #l1is="l1i.n.v1.prefetcher--eip+sets--8.json"
    #l1is="l1i.n.v1.prefetcher--eip+sets--4+replacement--lru.json"
    #l1is="l1i.n.v1.sets--4+replacement--lru.json"
    #l1is="l1i.n.v1.sets--262144.json"
    #l1is="l1i.n.v1.sets--4194304+prefetcher--eip.json" # BROKEN
    l1ds="l1d.n.v1..json"
    #l1ds="l1d.n.vcs..json"
    #l1ds="l1d.n.v1.replacement--random.json"
    #l1ds="l1d.n.v1.prefetcher--berti_4kb+pq_size--32+mshr_size--64.json"
    #l1ds="l1d.n.v1.prefetcher--berti_4kb.json"
    #l1ds="l1d.n.v1.prefetcher--berti_4kb+sets--512.json"
    #l1ds="l1d.n.v1.prefetcher--berti_4kb+sets--4194304.json"
    #l1ds="l1d.n.v1.prefetcher--stride_v1.json"
    #l1ds="l1d.n.v1.sets--2097152.json"
    #l2cs="l2c.n.v1..json"
    l2cs="l2c.n.vcs..json"
    #l2cs="l2c.n.vcs.thread_backup_threshold--100000000.json"
    #l2cs="l2c.n.v1.replacement--random.json"
    #l2cs="l2c.n.v1.prefetcher--pythia_4kb.json"
    #l2cs="l2c.n.v1.prefetcher--pythia_4kb+latency--20.json"
    #l2cs="l2c.n.v1.prefetcher--pythia_4kb+sets--8192.json"
    #l2cs="l2c.n.v1.prefetcher--pythia_4kb+sets--4194304.json"
    #l2cs="l2c.n.v1.prefetcher--bop_v1.json"
    #l2cs="l2c.n.v1.sets--4194304.json"

    #cores="core.$n.v2..json" #core.$n.v1.branch_predictor--cheating.json core.$n.v1.btb--cheating_btb.json core.$n.v1.branch_predictor--cheating+btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    cores="core.$n.vcs..json" #core.$n.v1.branch_predictor--cheating.json core.$n.v1.btb--cheating_btb.json core.$n.v1.branch_predictor--cheating+btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #cores="core.$n.v2.branch_predictor--cheating+btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #cores="core.$n.v2.btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #cores="core.$n.v2.branch_predictor--cheating.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #cores="core.$n.v2.branch_predictor--cheating.json core.$n.v2.btb--cheating_btb.json core.$n.v2.branch_predictor--cheating+btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #cores="core.$n.v1.sq_size--144.json"
    #cores="core.$n.v2.page_size--4096.json"
    #cores="core.$n.v1.page_size--4096+branch_predictor--cheating+btb--cheating_btb.json"
    #cores="core.$n.v2.btbreg_fix--true.json"
    #cores="core.$n.v2.fetch_width--32+full_fetch--true.json"
    #cores="core.$n.v2.xs2--true.json"
    #cores="core.$n.v2.xs2--true+full_fetch--true.json"
    llcs="llc.$n.v2..json"
    #llcs="llc.$n.vcs..json"
    #llcs="llc.$n.v2.sets--8192.json"
    #llcs="llc.$n.v2.replacement--random.json"
    #llcs="llc.$n.v2.prefetcher--next_line.json"
    #llcs="llc.$n.v2.prefetcher--spp_dev.json"
    #llcs="llc.$n.v2.sets--4194304.json"
    memories="memory.$n.v2..json"
    #memories="memory.$n.v2.bandwidth--2x.json"
    #memories="memory.$n.v2.bandwidth--16x.json"
    #memories="memory.$n.v2.latency--2x.json"
    #memories="memory.$n.v2.data_rate--1600.json"
    #memories="memory.$n.v2.instant--true.json"
    #memories="memory.$n.v2.bank_rows--67108864.json"
    tlbs="tlbs.n.v1..json" # tlbs.n.v1.dtlb-ways--8.json"
    #tlbs="tlbs.n.v1.num_levels--5.json"
    #tlbs="tlbs.n.v1.huge_page--true.json" # BROKEN
    #tlbs="tlbs.n.v1.stlb-ways--24.json tlbs.n.v1..json" # tlbs.n.v1.dtlb-ways--8.json"
    #tlbs="tlbs.n.v1.instant--true.json" # tlbs.n.v1.dtlb-ways--8.json"

    configdir="configs"

    for l1i in $l1is; do
        for l1d in $l1ds; do
            for l2c in $l2cs; do
                for core in $cores; do
                    for llc in $llcs; do
                        for memory in $memories; do
                            for tlb in $tlbs; do
                                #echo ./config.sh "$configdir/$core" "$configdir/$l1i" "$configdir/$l1d" "$configdir/$l2c" "$configdir/$llc" "$configdir/$memory" "$configdir/$tlb"
                                #./config.sh "$configdir/$core" "$configdir/$l1i" "$configdir/$l1d" "$configdir/$l2c" "$configdir/$llc" "$configdir/$memory" "$configdir/$tlb"
                                #make -j
                                python3 build.py "$configdir/$core" "$configdir/$l1i" "$configdir/$l1d" "$configdir/$l2c" "$configdir/$llc" "$configdir/$memory" "$configdir/$tlb"
                            done
                        done
                    done
                done
            done
        done
    done
done
