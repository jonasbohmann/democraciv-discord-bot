import csv

"""STV Calculator by Chemiczny_Bogdan.
    
    See this for details: https://gist.github.com/jonasbohmann/adadbe6c2c77a748b8e89d9d10ead074"""

elimset = set()


def count(v, w, n):
    c = [0] * len(n)
    for j in range(len(v)):
        e = v[j]
        if '1' in e:
            i = e.index('1')
            c[i] += w[j]
    return c


def winupdate(i, v, w, c, q, output):
    factor = 1 - q / c[i]
    output += "\n\nWinning ballots go to next round reweighed by a factor of " + str(factor)
    for c in range(len(v)):
        e = v[c]
        if e[i] == '1':
            for j in range(len(e)):
                e[j] = str(int(e[j]) - 1)
            if '1' in e:
                while e.index('1') in elimset:
                    for j in range(len(e)):
                        e[j] = str(int(e[j]) - 1)
                    if '1' not in e:
                        break
            w[c] = factor * float(w[c])
    elimset.add(i)
    return


def lossupdate(i, v):
    for c in range(len(v)):
        e = v[c]
        if e[i] == '1':
            for j in range(len(e)):
                e[j] = str(int(e[j]) - 1)
            if '1' in e:
                while e.index('1') in elimset:
                    for j in range(len(e)):
                        e[j] = str(int(e[j]) - 1)
                    if '1' not in e:
                        break
    elimset.add(i)
    return


def main(_seats, csvfile, quota):
    output = ""
    seats = _seats
    seatsleft = seats
    votes = []
    voteweights = []

    with open(f"db/stv/{csvfile}") as file:
        lines = csv.reader(file)
        f = 0
        for l in lines:
            if f == 0:
                namelist = l
                f = 1
                names = []
                for candname in namelist:
                    if candname:
                        names.append(candname)
                    else:
                        break
                wid = len(names)

            else:
                gl = []
                for i in range(wid):
                    e = l[i]
                    if e == 'Abstain':
                        gl.append('0')
                    else:
                        gl.append(e)
                votes.append(gl)
                voteweights.append(1)
        if quota == 0:
            quota = len(votes) / seats
            output += "\n\nThe Hare quota equals " + str(quota)
        elif quota == 1:
            quota = int(len(votes) / (seats + 1)) + 1
            output += "\n\nThe Droop quota equals " + str(quota)
        else:
            output += "\n\n#Invalid quota."
            return output

    candidatesleft = len(names)

    nameline = ' '.join(['{:^7.7}'.format(nam) for nam in names])

    n = 1
    while seatsleft > 0:
        output += f"\n\n#Round {str(n)}\n"
        foundwinner = 0
        actcount = count(votes, voteweights, names)
        output += nameline
        output += ' '.join(['{:^7.3f}'.format(i) for i in actcount])
        w = 0
        leastvotes = len(votes)
        for cand in actcount:
            if cand >= quota:
                output += "\n#" + names[w] + " won a seat!\n"
                winupdate(w, votes, voteweights, actcount, quota, output)
                seatsleft -= 1
                candidatesleft -= 1
                foundwinner = 1
            else:
                if leastvotes > cand > 0:
                    leastvotes = float(cand)
                    loser = int(w)
            w += 1
        if foundwinner == 0:
            output += "\n#" + names[loser] + " lost!\n"
            lossupdate(loser, votes)
            candidatesleft -= 1
        if seatsleft == candidatesleft:
            winset = set(range(len(names))) - elimset
            output += "#" + "and ".join([names[i] for i in list(winset)]) + " win the remaining seats!"
            break
        n += 1

    return output
