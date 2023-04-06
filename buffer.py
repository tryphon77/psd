import sys
sys.path.append('..')

import numpy, codecs, os
ascii_table = "".join([chr(i) for i in range(255)])

class Buffer():
	def __init__(self, 
				 data = None,
				 start = 0,
				 stop = None, 
				 index = 0,
				 little_endian = False):
		if data is not None:
#			self.data = numpy.array(data, dtype = numpy.uint8)
			self.data = data
		else:
			self.data = []
		self.start = start
		self.stop = stop
		self.index = index
		
		self.states = []
		
		self.current_bit = self.current_nib = 0
		self.byte_of_nib = self.byte_of_bit = 0
		self.last_byte_of_nibs = 0
	
	def save_state(self):
		self.states += [(self.index, self.current_bit, self.current_nib)]
		
	def restore_state(self):
		self.index, self.current_bit, self.current_nib = self.states.pop()

	def __len__(self):
		return len(self.data) - self.start

	@staticmethod
	def load(path, offset = 0):
		f = open(path, 'rb')
		data = bytearray(f.read())
		f.close()
		return Buffer(data[offset : ])

	def save(self, path):
		f = open(path, 'wb')
		f.write(bytearray(self.data))
		f.close()
	
	def __getitem__(self, val):
		if isinstance(val, slice):
			return Buffer(self.data[self.start + val.start : self.start + val.stop])
		#Buffer(self.data, start = self.start + val.start, stop = self.start + val.stop)
		
		return self.data[self.start + val]
		
	def set_index(self, pos = 0):
		self.index = pos
		self.current_bit = self.current_nib = 0
		self.byte_of_nib = self.byte_of_bit = 0
		self.last_long_of_nibs = 0
	
	def set_index_at_end(self):
		self.set_index(len(self))
	
	def advance_index_by(self, val):
		self.set_index(self.index + val)
	
	def extract(self, size, pos = -1):
		if pos == -1:
			pos = self.index
		return self[pos : pos + size]
	
	def is_eof(self):
#		self.current_bit = self.current_nib = 0
		return self.index >= len(self)

	def read_bit(self):
		val = (self.read_b(self.index) >> (7 - self.current_bit)) & 1
		self.current_bit += 1
		if self.current_bit == 8:
			self.index += 1
			self.current_bit = 0
		return val
	
	def read_bits(self, n):
		res = 0
		for _ in range(n):
			res *= 2
			res += self.read_bit()
		return res
	
	def read_nibble(self):
		val = (self.read_b(self.index) >> (4 - 4 * self.current_nib)) & 15
		self.current_nib += 1
		if self.current_nib == 2:
			self.index += 1
			self.current_nib = 0
		return val

	def read_b(self, pos = -1, signed = False):
		if pos == -1:
			pos = self.index
			self.index += 1
		val = self[pos]
		
		if signed and val >= 128:
			val -= 256

		return val

	def read_w(self, pos = -1, signed = False):
		if pos == -1:
			pos = self.index
			self.index += 2
		val = self[pos] * 256 + self[pos + 1]

		if signed and val >= 32768:
			val -= 65536

		return val

	def read_l(self, pos = -1, signed = False):
		if pos == -1:
			pos = self.index
			self.index += 4
		val = self[pos] * 0x1000000 + self[pos + 1] * 0x10000 \
			  + self[pos + 2] * 0x100 + self[pos + 3]

		if signed and val >= 0x80000000:
			val -= 0x100000000
		
		if not signed and val < 0:
			val += 0x100000000

		return val
	
	def read_string(self, pos = -1, table = ascii_table, end_char = 0x00, n_chars = 1000000):
		if pos >= 0:
			self.save_state()
		res = u''
		i = 0

		while i < n_chars:
#			 if encoding_bits == 8:
#				 c = self.read_b(pos)
#				 pos += 1
#			 elif encoding_bits == 16:
#				 c = self.read_w(pos)
#				 pos += 2
#			 else:
#				 print 'invalid encoding_bits: %d' % encoding_bits

			if type(table) is str:
				char_id = self.read_b()
				if char_id < len(table):
					c = table[char_id]
				else:
					print("char |%02X| not in encoding" % char_id)
					c = "[%02X]" % char_id
			else:
				c, _ = table.read_buffer(self)
			if c == end_char:
				break

			if c:
				res += c
			else:
				res += '?'
			i += 1
		
		if pos >= 0:
			self.restore_state()
		return res

	def find_b(self, v, pos = -1):
		if pos == -1:
			pos = self.index
			update_index = True
		
		while self.read_b(pos) != v:
			pos += 1
		
		if update_index:
			self.set_index(pos)
		
		return pos
	
	def find_relative(self, seq):
		res = []
		self.save_state()
		self.set_index(0)
		
		i = 0
		while i < len(self) - len(seq):
			delta = self.read_b(i) - seq[0]

			i0 = i
			found = True
			for j in seq:
#				print '%02X/%02X' % (self.read_b(i), j)
				if j is not None:
					if self.read_b(i) != j + delta:
						found = False
						break
				i += 1
			
			if found:
				res += [i0]
			i = i0 + 1

		self.restore_state()
		return res
					
						

	def __str__(self):
		_end = min(self.index + 0x1000, len(self))
		return 'Buffer ; length = %x ; index = %x\ndata = ...' % (len(self), self.index)\
			+ ' '.join(['%02x' % self[x] for x in range(self.index, _end)])

	def dump(self, start = 0, end = -1, tbl = ascii_table):
		if end < 0:
			end = len(self)

		res = []
		line = u''
		line_str = u''

		pos = line_start = start
		while pos < end:
			v = self.read_b(pos)
#			print 'v =', v, tbl[v], v in tbl
			line += ('%02X ' % v)
			if v in tbl and len(tbl[v]) == 1:
				line_str += tbl[v]
			else:
				line_str += '.'
			pos += 1
			if pos % 16 == 0:
#				 if pos % 0x1000 == 0:
#					 print '%X/%X' % (pos, end)
				res += ['%08X : %s | %s' % (line_start, line, line_str)]
				line_start = pos
				line = u''
				line_str = u''
		res += ['%08X : %s | %s' % (line_start, line, line_str)]
		return '\n'.join(res)
				

# ========================================================================
# =						   Write methods							  =
# ========================================================================
	def enlarge(self, sz):
		self._check_pos(sz - 1)

	def _check_pos(self, pos):
		if pos >= len(self.data):
			self.data += bytearray([0]) * (pos - len(self.data) + 1)
#		self.length = max(self.length, pos + 1)

	def write_b(self, val, pos = -1, signed = False):
		if signed and val < 0:
			return self.write_b(val + 0x100, pos)
		if pos == -1:
			pos = self.index
			self.index += 1
		else:
			self.byte_of_nib = self.byte_of_bit = 0

		self._check_pos(pos)
		self.data[pos] = val
		return pos
		
	def write_w(self, val, pos = -1, signed = False):
		if signed and val < 0:
			return self.write_w(val + 0x10000, pos)
		if pos == -1:
			pos = self.index
			self.index += 2
		else:
			self.byte_of_nib = self.byte_of_bit = 0
			
		self._check_pos(pos + 1)
		self.data[pos] = val // 0x100
		self.data[pos + 1] = val % 0x100
		return pos
 
	def write_l(self, val, pos = -1, signed = False):
		if signed and val < 0:
			return self.write_l(val + 0x100000000, pos)
		if pos == -1:
			pos = self.index
			self.index += 4
		else:
			self.byte_of_nib = self.byte_of_bit = 0

		self._check_pos(pos + 3)
		self.data[pos] = val // 0x1000000
		self.data[pos + 1] = (val // 0x10000) % 0x100
		self.data[pos + 2] = (val // 0x100) % 0x100
		self.data[pos + 3] = val % 0x100
		return pos

	def write_hex(self, string, pos_ = -1):
		if pos_ == -1:
			pos = self.index
		else:
			pos = pos_

		c_string = string.replace(" ", "")
		length = len(c_string)//2
		array = bytearray([0]) * length
		last_p = p = pos
		update_p = False
	
		for i in range(length):
			code = c_string[2*i : 2*i + 2]
	
			if code == '**':
				array[i] = self.read_b(p)
				update_p = True
			elif code == '++':
				array[i] = self.read_b(last_p)
				last_p += 1
			else:
				array[i] = int(code, 16)
				if update_p:
					last_p = p
					update_p = False
			p += 1

		pos = self.write(array, pos_)
		
		return pos


	def write(self, buf, pos = -1):
		if isinstance(buf, str):
			return self.write_hex(buf, pos)
		else:
			if pos == -1:
				pos = self.index
				self.index += len(buf)
			self._check_pos(pos + len(buf) - 1)
	#		print 'len before =', len(self)
			if type(buf) in [list, bytearray]:
				self.data[pos : pos + len(buf)] = buf[:len(buf)]
			else:
				self.data[pos : pos + len(buf)] = list(buf.data[:len(buf)])
	#		print 'len after =', len(self)
	#		self.index += len(buf)
			return pos

	def write_nibble(self, v, mode_ = 0):
#		print type(self.byte_of_nib), 'byte_of_nib = %X' % self.byte_of_nib
#		print 'write nibble %X, byte_of_nib = %08X' % (v, self.byte_of_nib)
		self.byte_of_nib *= 16
		self.byte_of_nib += v
		self.current_nib += 1
		if self.current_nib == 8:
			if mode_ == 1:
				self.byte_of_nib ^= self.last_byte_of_nibs
			self.write_l(self.byte_of_nib)
			self.last_byte_of_nibs = self.byte_of_nib
			self.current_nib = 0
			self.byte_of_nib = 0

	def write_nibbles(self, list_, mode_):
		for nib in list_:
			self.write_nibble(nib, mode_)

	def include(self, path, pos = -1):
		if path.endswith('.L68'):
			self.include_L68(path)
		else:
			f = open(path, 'rb')
			code = bytearray(f.read())
			f.close()
			
			# print '%s : %X bytes to write' % (path, len(code))
			self.write(code, pos)

	def include_L68(self, path):
		def is_hex(x):
			for c in x:
				if c not in '0123456789ABCDEF':
					return False
			return True

		f = open(path, 'r')
		code = f.read()
		f.close()

		for line in code.split('\n'):
			if line != '':
				addr = line[:8]

				if is_hex(addr):
					addr = int(addr, 16)
					i = 10
					while True:
						c = line[i : i + 2]
						if is_hex(c):
							c = int(c, 16)
#							print 'write %02X to %08x' % (c, addr)
							self.write_b(c, addr)
							i += 2
							addr += 1

							if line[i] == ' ':
								i += 1
						else:
							break

	def write_string(self, 
					 s, 
					 pos = -1, 
					 encoding_bits = 8, 
					 table = ascii_table, 
					 end_char = -1, 
					 fill_char = 0x20, 
					 size = -1, 
					 control_codes = False, 
					 cc_delimiters = '[]'):
		
		write_method = [self.write_b, self.write_w, None, self.write_l][encoding_bits//8 - 1]
		delta = encoding_bits//8
		
#		print 'write_method=', write_method

		if pos == -1:
			increment_at_end = True
			_pos = self.index
		else:
			increment_at_end = False
			_pos = pos

		i = 0
		while i < len(s):
			if (size > 0) and (i >= size):
				print ('string [%s] too long, broken at pos %d' % (s, i))
				break
			c = s[i]
#			print 'c = %s' % c
			if c == cc_delimiters[0]:
				if control_codes:
					e = s.index(cc_delimiters[1], i)
					code = int(s[i + 1 : e], 16)
#					print 'write %02X at %X' % (code, _pos)
					write_method(code, _pos)
					_pos += delta
					i = e + 1
				else:
					e = s.index(cc_delimiters[1], i)
					code = s[i : e + 1]
					if code in table:
#						print 'write %s at %X' % (code, _pos)
						write_method(table.get_code(code), _pos)
					else:
						print ('unknown control code : %s' % code)
						exit()
					_pos += delta
					i = e + 1					
			elif type(table) is str and c in table:
				self.write_b(table.index(c))
				_pos += 1
				i += 1
			elif c in table:
#				print '[%s] : @write %s at %X' % (c, table.index(c), _pos)
#				write_method(table.get_code(c), _pos)
				for x in table.get_code(c):
					self.write_b(x, _pos)
					_pos += 1
				i += 1
			else:
				print ('unknown char : |%s|' % c)
				# print table.chars
				# print table.chars_
				# print table.codes
				exit()
				i += 1
				
		if end_char != -1:
			write_method(end_char, _pos)
			_pos += delta
		
		if size > 0 and len(s) < size:
			for _ in range(size - len(s)):
				write_method(fill_char, _pos)
				_pos += delta
		
		if increment_at_end:
			self.index = _pos
		
		

	#============================================================================
	def find(self, pattern, start = 0, end = -1):
		if end < 0:
			end = len(self)

		pattern = pattern.replace(' ', '')
		
		if len(pattern) % 2:
			pattern = '0' + pattern
		
		cut_pattern = [pattern[i : i + 2] for i in range(0, len(pattern), 2)]
		
		self.save_state()
		self.set_index(0)
		
		res = []

		while self.index < end and not self.is_eof():
			self.save_state()
			found = True
			for c in cut_pattern:
				read_val = self.read_b()
				if not '*' in c:
					val = int(c, 16)
					if val != read_val:
						found = False
						break
			self.restore_state()
			if found:
				res += [self.index]
			self.read_b()
		
		self.restore_state()
		return res
	
	def replace(self, a, b):
		pos_list = self.find(a)
		for pos in pos_list:
			self.write_hex(b, pos)
	
	def copy(self, start, end, dest):
		self.write(self.data[start : end], dest)
	
	def align(self, x = 2, val = 0):
		while self.index % x:
			self.write_b(val)
		return self.index
	
	def compile(self, path, sym_table = {}, update_symbols = True):
		def remove_comment(text):
			if ';' in text:
				i = text.index(';')
				return text[:i]
			return text

		def update_sym_table(table, buf):
			buf.set_index(8)
			
			while not buf.is_eof():
#				print hex(buf.index)
				a, b, c, d = buf.read_b(), buf.read_b(), buf.read_b(), buf.read_b()
				addr = (d << 24) + (c << 16) + (b << 8) + a
				buf.read_b()
				nmsz = buf.read_b()
				nm = buf.read_string(n_chars = nmsz)
				
				table[nm] = addr

		text = u''
		for s in sym_table.keys():
			text += '%s\tequ\t0x%x\n' % (s, sym_table[s])
		
		reg_aliases = []
		
		f = codecs.open(path, 'r', 'utf-8-sig')
		lines = f.readlines()
		f.close()
		
		for line in lines:
	
#			print '============================================'
#			print line
#			print 'setreg' in line
			if 'setreg' in line:
				line = remove_comment(line)
				i = line.index('setreg')
				left = line[:i].strip()
				right = line[i + 6:].strip()
				reg_aliases += [(left, right)]
#				print '%s -> %s' % (left, right)
			else:
				for left, right in reg_aliases:
					line = line.replace(left, right)
			
				text += line
		
		bin_dir = os.path.dirname(__file__)
		dirname = os.path.dirname(path)
		
		f = codecs.open('%s/__temp__.asm' % dirname, 'w', 'utf-8')
		f.write(text)
		f.close()
	
		os.system('%s\\bin\\asm68k.exe /o op+ /o os+ /o ow+ /o oz+ /o oaq+ /o osq+ /o omq+ %s\\__temp__.asm,%s\\__temp__.bin,%s\\__temp__.sym'\
				  % (bin_dir, dirname, dirname, dirname))
				
		sym_buf = Buffer.load('%s/__temp__.sym' % dirname)

		if update_symbols:
			update_sym_table(sym_table, sym_buf)
			# print "symbols:"
			# print sym_table

		binary = Buffer.load('%s/__temp__.bin' % dirname)
		binary.set_index(6)
		
		while binary.index + 6 < len(binary):
#			print hex(binary.index)
			binary.read_b()
			a, b, c, d = binary.read_b(), binary.read_b(), binary.read_b(), binary.read_b()
			addr = (d << 24) + (c << 16) + (b << 8) + a
			a, b, c, d = binary.read_b(), binary.read_b(), binary.read_b(), binary.read_b()
			length = (d << 24) + (c << 16) + (b << 8) + a
			
			source_addr = binary.index
#			print 'Copying %x bytes at %x' % (length, addr)
			self.write(binary[source_addr : source_addr + length], addr)
			
			binary.set_index(source_addr + length)
		
		self.index = addr + length

if __name__ == '__main__':
	a = Buffer()
	b = Buffer()
	for i in range(0x10):
		a._check_pos(i)
	b.write_b(0x42)
	
	a.dump()
	b.dump()	

