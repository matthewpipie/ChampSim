ns="1 4"
#ns="4"

for n in $ns; do
    echo "starting n=$n"


#core.1.v1..json
#core.4.v1..json
#l1d.n.v1..json
#l1d.n.v1.prefetcher--stride_v1.json
#l1i.n.v1..json
#l1i.n.v1.prefetcher--next_line.json
#l2c.n.v1..json
#l2c.n.v1.prefetcher--bop_v1.json
#llc.1.v1..json
#llc.4.v1..json
#memory.1.v1..json
#memory.4.v1..json
#tlbs.n.v1..json

    l1is="l1i.n.v1..json l1i.n.v1.prefetcher--next_line.json"
    l1ds="l1d.n.v1..json l1d.n.v1.prefetcher--stride_v1.json"
    l2cs="l2c.n.v1..json l2c.n.v1.prefetcher--bop_v1.json"

    cores="core.$n.v1..json"
    llcs="llc.$n.v1..json"
    memories="memory.$n.v2..json memory.$n.v2.bandwidth--4x.json"
    tlbs="tlbs.n.v1..json"

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
                                ./build.py "$configdir/$core" "$configdir/$l1i" "$configdir/$l1d" "$configdir/$l2c" "$configdir/$llc" "$configdir/$memory" "$configdir/$tlb"
                            done
                        done
                    done
                done
            done
        done
    done
done
