import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.settimeout(2)
try:
    s.sendto(b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00030010\n", ("192.168.178.40", 9302))
    print("reaches the console:", s.recvfrom(512)[0][:15])
except Exception as e:
    print("blocked:", e)
