Салахутдинов Роберт ИКБО 24-25
Практическая 1
Задание 1
labex:/etc/ $ grep -o '^[^:]*' passwd | sort
Задание 2
labex:/etc/ $ sort -k2 -nr /etc/protocols | head -5 | awk '{print $2, $1}'
Задание 3
labex:~/ $ echo '#!/bin/bash' > banner        
labex:~/ $ echo 'text="$*"' >> banner
labex:~/ $ echo 'n=${#text}' >> banner
labex:~/ $ echo 'line=$(printf "%*s" "$((n+2))" "" | tr " " "-")' >> banner
labex:~/ $ echo 'echo "+$line+"' >> banner
labex:~/ $ echo 'echo "| $text |"' >> banner
labex:~/ $ echo 'echo "+$line+"' >> banner  
labex:~/ $ chmod +x banner        
labex:~/ $ cat banner
labex:~/ $ ./banner Hello from RTU MIREA!
labex:~/ $ ./banner Hi
Задание 4
labex:~/ $ cat > hello.cpp << 'EOF'
#include <iostream>
void hello(int n) {
    std::cout << "hello world" << std::endl;
}
int main() {
    hello(1);
    return 0;
}
EOF
labex:~/ $ cat hello.cpp
labex:~/ $ grep -oE '\b[A-Za-z_][A-Za-z0-9_]*\b' hello.cpp | sort -u
Задание 5
labex:~/ $ ls -l banner
labex:~/ $ cat > reg << 'EOF'
#!/bin/bash
chmod +x "$1"
cp "$1" /usr/local/bin/
echo "Registered: $1 -> /usr/local/bin/$1"
EOF
labex:~/ $ cat reg
labex:~/ $ chmod +x reg
labex:~/ $ sudo ./reg banner
labex:~/ $ which banner
labex:~/ $ ls -l /usr/local/bin/banner
labex:~/ $ cd /
labex:// $ banner Hello from RTU MIREA
Задание 6
labex:project/ $ cat > test.c << 'EOF'
// This is a C program
#include <stdio.h>
int main() { return 0; }
EOF
labex:project/ $ cat > app.js << 'EOF'
// JavaScript app
console.log("hello");
EOF
labex:project/ $ cat > script.py << 'EOF'
# Python script
print("hello")
EOF
labex:project/ $ cat > clean.c << 'EOF'
#include <stdio.h>
int main() { return 0; }
EOF
labex:project/ $ cat > check_comment << 'EOF'
#!/bin/bash
for file in *.c *.js *.py; do
  [[ -e $file ]] || continue
  first_line=$(head -n 1 "$file")

  case $file in
    *.c|*.js)
      if [[ $first_line =~ ^[[:space:]]*(//|/\*) ]]; then
        echo "$file: YES (comment: $first_line)"
      else
        echo "$file: NO"
      fi
      ;;
    *.py)
      if [[ $first_line =~ ^[[:space:]]*# ]]; then
        echo "$file: YES (comment: $first_line)"
      else
        echo "$file: NO"
      fi
      ;;
  esac
done
EOF                                                                      
labex:project/ $ chmod +x check_comment      
./check_comment
Задание 7
labex:project/ $ mkdir -p testdir/sub1 testdir/sub2 testdir/sub3

echo "hello" > testdir/a.txt
echo "hello" > testdir/sub1/b.txt
echo "hello" > testdir/sub2/c.txt
echo "world" > testdir/d.txt
echo "unique" > testdir/sub3/e.txt
labex:project/ $ find testdir -type f
testdir/sub1/b.txt
testdir/sub2/c.txt
testdir/sub3/e.txt
testdir/a.txt
testdir/d.txt
labex:project/ $ find testdir -type f -exec md5sum {} + | sort | uniq -D -w32
Задание 8
labex:project/ $ mkdir -p project/sub
echo "1" > project/a.txt
echo "2" > project/b.txt
echo "3" > project/sub/c.txt
echo "4" > project/d.log
labex:project/ $ cat > archive_by_ext << 'EOF'
#!/bin/bash
mapfile -t files < <(find "$1" -type f -name "*$2")
tar -cf archive.tar "${files[@]}"
EOF

chmod +x archive_by_ext
./archive_by_ext project .txt
tar -tf archive.tar
Задание 9
labex:project/ $ cat > spaces2tab << 'EOF'
#!/bin/bash
sed 's/    /\t/g' "$1" > "$2"
EOF

chmod +x spaces2tab
labex:project/ $ printf 'a    b    c\n' > in.txt
./spaces2tab in.txt out.txt
cat -A out.txt
Задание 10
abex:project/ $ cat > empty_files << 'EOF'
#!/bin/bash
find "$1" -type f -empty
EOF

chmod +x empty_files
labex:project/ $ mkdir -p d/sub
touch d/a.txt d/sub/b.txt
echo "text" > d/c.txt
./empty_files d
