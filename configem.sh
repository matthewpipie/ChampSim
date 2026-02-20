#ns="1 4"
#ns="4"
ns="1"

for n in $ns; do
    echo "starting n=$n"

    #l1is="l1i.n.v1..json"
    l1is="l1i.n.v1.prefetcher--eip.json"
    #l1is="l1i.n.v1.sets--4194304.json"
    #l1is="l1i.n.v1.sets--4194304+prefetcher--eip.json"
    #l1ds="l1d.n.v1..json"
    #l1ds="l1d.n.v1.prefetcher--berti+pq_size--32+mshr_size--64.json"
    l1ds="l1d.n.v1.prefetcher--berti.json"
    #l1ds="l1d.n.v1.sets--4194304.json"
    #l2cs="l2c.n.v1..json"
    l2cs="l2c.n.v1.prefetcher--pythia.json"
    #l2cs="l2c.n.v1.sets--4194304.json"

    cores="core.$n.v1..json" #core.$n.v1.branch_predictor--cheating.json core.$n.v1.btb--cheating_btb.json core.$n.v1.branch_predictor--cheating+btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #cores="core.$n.v1.branch_predictor--cheating+btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #cores="core.$n.v1..json core.$n.v1.branch_predictor--cheating.json core.$n.v1.btb--cheating_btb.json core.$n.v1.branch_predictor--cheating+btb--cheating_btb.json" # "core.$n.v1.mispredict-penalty--0.json" 
    #llcs="llc.$n.v1..json"
    llcs="llc.$n.v1.prefetcher--next_line.json"
    #llcs="llc.$n.v1.prefetcher--spp_dev.json"
    #llcs="llc.$n.v1.sets--4194304.json"
    memories="memory.$n.v2..json"
    #memories="memory.$n.v2.bandwidth--4x.json"
    #memories="memory.$n.v2.bandwidth--2x.json"
    #memories="memory.$n.v2.latency--2x.json"
    #memories="memory.$n.v2.instant--true.json"
    tlbs="tlbs.n.v1..json" # tlbs.n.v1.dtlb-ways--8.json"
    #tlbs="tlbs.n.v1.stlb-ways--24.json tlbs.n.v1..json" # tlbs.n.v1.dtlb-ways--8.json"

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
