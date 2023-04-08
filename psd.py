# -*- coding: utf-8 -*-

import png
import numpy as np
np.set_printoptions(formatter={'int':hex})

from buffer import Buffer

# A PngArray is a numpy.array describing an image in the pypng module conevntion
# a w*h RGBA image is described as a (h, w*4) image, components are in ARGB order

write_version_info = True
write_resolution_info = True
write_unicode_layer_name = True


def load_png(path):
	r = png.Reader(path)
	w, h, arr, info = r.read()

	arr = np.array(list(arr), dtype=np.uint8)
	arr.shape = (h, w*4)
	
	return arr

def get_bounding_box(a):
	array = a[:,:]
	array.dtype = np.uint32
	height, width = array.shape
	top = 0
	while top < height and not array[top, :].any():
		top += 1
 			
	left = 0
	while left < width and not array[:, left].any():
		left += 1
 			
	bottom = height - 1
	while bottom >= 0 and not array[bottom, :].any():
		bottom -= 1
	bottom += 1
	
	right = width - 1
	while right >= 0 and not array[:, right].any():
		right -= 1
	right += 1

	# print("get_bounding_box: top=%d left=%d bottom=%d right=%d" % (top, left, bottom, right))	
	return top, left, bottom, right

def write_pascal_string(buf, s):
	# Pascal String
	# 1 byte : length of the string
	# utf8 encoded string
	# padded with 0 so that total length is a multiple of 4
	data = list(s.encode("utf8"))
	buf.write_b(len(data))
	buf.write(data)
	i = len(data) + 1
	while i%4 != 0:
		buf.write_b(0)
		i += 1

def write_offset(buf, offset_pos):
	offset = buf.index - offset_pos - 4
#	print("offset : from %X to %X = %X at %X" % (offset_pos + 4, buf.index, offset, offset_pos))
	buf.write_l(offset, pos=offset_pos)

def writeUTF16(buf, s):
	# Unicode String
	# 4 : length of the string (nb of chars, not number of bytes)
	# utf-16 encoded string
	# 2 : 00 00
	buf.write_l(len(s))
	data = list(s.encode("utf-16-be"))
	buf.write(data)
	buf.write_w(0)

class PsdChannel:
	def __init__(self,
        id,
		data
	):
		self.id = id
		self.data = data
		self.height, self.width = data.shape
		self.size = (self.width, self.height)
		# print("Channel %d: size=(%s)" % (self.id, self.size))
	
	def write_data(self, buf, compression=0):
		# @TODO : write RLE compressed data
		buf.write_w(compression)
		
		if compression == 0:
			buf.write(self.data.flatten())
	
	def __len__(self):
		return self.height * self.width + 2

class PsdLayer():
	def __init__(self, 
		name = '', 
		offset = (0, 0),
		size=None,
		surface  = None,
		channels = [],
		image = None
	):
		# print("PsdLayer")
		self.name = name

		if image is not None:
			top, left, bottom, right = get_bounding_box(image)
			x0, y0 = offset
			offset = (x0 + left, y0 + top)

			cropped_image = image[top : bottom, 4*left : 4*right]				
			self.channels = [
				PsdChannel(-1, cropped_image[:, 3::4]),
				PsdChannel(0, cropped_image[:, 2::4]),
				PsdChannel(1, cropped_image[:, 1::4]),
				PsdChannel(2, cropped_image[:, 0::4])
			]
			
			size = (right - left, bottom - top)

		else:
			self.channels = channels

		self.offset = offset
		self.nb_channels = len(self.channels)
		self.is_visible = True
		
		if size is None:
			w, h = self.channels[0].size
			self.size = (w, h)
		else:
			self.size = size

		self.color_mode = 3
		# print("""Layer "%s": size=%s, offset=%s""" % (self.name, self.size, self.offset))

	def hide(self):
		self.is_visible = False
	
	def show(self):
		self.is_visible = True
		
	def get_data(self, order="ARGB"):
		# return data as a PngArray (order can be modified)

		w, h = self.size
		res = np.zeros((h, w, 4), dtype = np.uint8)
		
		res[:,:,order.index("A")] = self.channels[0].data # A
		res[:,:,order.index("R")] = self.channels[1].data # R
		res[:,:,order.index("G")] = self.channels[2].data # G
		res[:,:,order.index("B")] = self.channels[3].data # B
		
		res.shape = (h, w*4)

		return res

	def save_as_png(self, path, crop=False):
		layer_data = self.get_data(order = "RGBA")
		png.from_array(layer_data, mode="RGBA").save(path)
		
	def get_bounding_box(self):
		left, top = self.offset
		width, height = self.size
		return top, left, top + height, left + width

# 	def draw_channels(self, a):
# 		for i, channel in enumerate(self.channels):
# 			h, w = channel.data.shape
# 			print(a.shape, channel.data.shape)
# 			a[i,:h,:w] = channel.data[:]

	def write_to_buffer(self, buf):		
		# 4 * 4 : Rectangle containing the contents of the layer. Specified as top, left, bottom, right coordinates
		top, left, bottom, right = self.get_bounding_box()
		buf.write_l(top)
		buf.write_l(left)
		buf.write_l(bottom)
		buf.write_l(right)
		
		# 2 : Number of channels in the layer
		buf.write_w(self.nb_channels)
		
		# 6 * number of channels : Channel information. 
		for channel in self.channels:			
			# 2 bytes for Channel ID: 0 = red, 1 = green, etc.;
			buf.write_w(channel.id, signed=True)
					
			# 4 bytes for length of corresponding channel data. (**PSB** 8 bytes for length of corresponding channel data.) See See Channel image data for structure of channel data.
			buf.write_l(len(channel))
					
		# 4 : Blend mode signature: '8BIM'
		buf.write_string("8BIM")
		
		# 4 : Blend mode key:		
		# 'pass' = pass through, 'norm' = normal, 'diss' = dissolve, 'dark' = darken, 'mul ' = multiply, 'idiv' = color burn, 'lbrn' = linear burn, 'dkCl' = darker color, 'lite' = lighten, 'scrn' = screen, 'div ' = color dodge, 'lddg' = linear dodge, 'lgCl' = lighter color, 'over' = overlay, 'sLit' = soft light, 'hLit' = hard light, 'vLit' = vivid light, 'lLit' = linear light, 'pLit' = pin light, 'hMix' = hard mix, 'diff' = difference, 'smud' = exclusion, 'fsub' = subtract, 'fdiv' = divide 'hue ' = hue, 'sat ' = saturation, 'colr' = color, 'lum ' = luminosity
		buf.write_string("norm")
		
		# 1 : Opacity. 0 = transparent ... 255 = opaque
		buf.write_b(255)

		# 1 : Clipping: 0 = base, 1 = non-base
		buf.write_b(0)

		# 1 : Flags:
		# 	bit 0 = transparency protected;
		# 	bit 1 = visible;
		# 	bit 2 = obsolete;
		# 	bit 3 = 1 for Photoshop 5.0 and later, tells if bit 4 has useful information;
		# 	bit 4 = pixel data irrelevant to appearance of document
		buf.write_b(0)
		
		# 1 : Filler (zero)
		buf.write_b(0)

		extra_data_field_length_pos_1 = buf.index
		# 4 : Length of the extra data field ( = the total length of the next five fields).
		buf.write_l(0) # <--------------------------------------
		
		
		
		
		
		# Variable : Layer mask data: See See Layer mask / adjustment layer data for structure. Can be 40 bytes, 24 bytes, or 4 bytes if no layer mask.
		buf.write_l(0)
		
		# Variable : Layer blending ranges: See See Layer blending ranges data.
		buf.write_l(0)
		
		# Variable : Layer name: Pascal string, padded to a multiple of 4 bytes.
		write_pascal_string(buf, self.name)	
		
		
		if write_unicode_layer_name:
			buf.write_string("8BIM")
			buf.write_string("luni")
			extra_data_field_length_pos = buf.index
			buf.write_l(0)
			writeUTF16(buf, self.name)
			write_offset(buf, extra_data_field_length_pos)

		write_offset(buf, extra_data_field_length_pos_1)
		
	def write_channels_data_to_buffer(self, buf, compression=0):
		for channel in self.channels:
			channel.write_data(buf, compression)

		
class PsdFile():
	def __init__(self, 
		size = (0, 0), 
		layers = [],
		color_mode = 3,
		palette = None
	):
		self.size = size
		self.layers = layers
		self.nb_layers = len(layers)
		self.color_mode = color_mode
		self.palette = palette		
	
	def add_layer(self, layer):
		# print("PsdFile.add_layer")
		assert type(layer) == PsdLayer
		
		self.layers.append(layer)
		self.nb_layers += 1
		
		top, left, bottom, right = layer.get_bounding_box()
		
		width, height = self.size

		# print("add_layer: top=%d left=%d bottom=%d right=%d width=%d height=%d" % (top, left, bottom, right, width, height))

		width = max(width, right)
		height = max(height, bottom)
		self.size = (width, height)
		
		# print("-> width=%d height=%d" % (width, height))
		
		if top < 0 or right < 0:
			print("Warning: lost data in layer [%s]" % layer.name)
			
	def remove_layer(self, layer):
		self.layers.remove(layer)
		self.nb_layers -= 1
		
	def get_by_name(self, name):
		for layer in self.layers:
			if layer.name == name:
				return layer
		raise Exception("Layer [%s] not found" % name)

	@staticmethod
	def from_images(images):
		res = PsdFile()
		
		for path in images:
			image = load_png(path)
			res.add_layer(PsdLayer(name=path, image=image))
		
		return res
			
	def save(self, path):
		buf = Buffer()
		self.write_to_buffer(buf)
		buf.index = 0
		buf.save(path)
	
	def write_to_buffer(self, buf):
		# =================================================================
		# File Header Section
		# =================================================================
		
		# 	Signature (4) : always equal to '8BPS' . Do not try to read the file if the signature does not match this value.
		buf.write_string("8BPS")
	
		# 	Version (2) : always equal to 1. Do not try to read the file if the version does not match this value. (**PSB** version is 2.)
		buf.write_w(1)
		
		# 	Reserved (6) : must be zero.
		buf.write("00 00 00 00 00 00")
		
		# 	The number of channels in the image (2), including any alpha channels. Supported range is 1 to 56.
		if self.color_mode < 3:
			buf.write_w(1)
		elif self.color_mode == 3:
			buf.write_w(4)

		width, height = self.size
		# 	The height of the image in pixels (4). Supported range is 1 to 30,000.
		buf.write_l(height)
		
		# 	The width of the image in pixels (4). Supported range is 1 to 30,000.
		buf.write_l(width)
		
		# 	Depth (2) : the number of bits per channel. Supported values are 1, 8, 16 and 32.
		buf.write_w(8)
		
		# 	The color mode of the file (2). Supported values are: Bitmap = 0; Grayscale = 1; Indexed = 2; RGB = 3; CMYK = 4; Multichannel = 7; Duotone = 8; Lab = 9.
		buf.write_w(self.color_mode)


		# =================================================================
		# Color Mode Data Section
		# =================================================================

		color_mode_data_section_pos = buf.index

		# 4 : The length of the following color data.
		buf.write_l(0)

		if self.color_mode < 3:
			# Indexed color images: length is 768; color data contains the color table for the image, in non-interleaved order.
			raise Exception("Indexed colors : not yet implemented")
		
		write_offset(buf, color_mode_data_section_pos)


		# =================================================================
		# Image Resources Section
		# =================================================================

		image_resources_section_pos = buf.index
		# 4 : Length of image resource section. The length may be zero.
		buf.write_l(0)
		
		# Image resources (Image Resource Blocks ).
		
		if write_resolution_info:
			# 4 : Signature: '8BIM'
			buf.write_string("8BIM")
			
			# 2 : # Unique identifier for the resource. 
			buf.write_w(0x3ED) # ResolutionInfo structure. See Appendix A in Photoshop API Guide.pdf
			buf.write_w(0) # no name
			buf.write_l(16) # length of the section
			buf.write_l(0x00600000) # Fixed hRes : Horizontal resolution in pixels per inch
			buf.write_w(1) # int16 hResUnit : 1=display horitzontal resolution in pixels per inch; 2=display horitzontal resolution in pixels per cm
			buf.write_w(1) # int16 widthUnitDisplay : width as 1=inches; 2=cm; 3=points; 4=picas; 5=columns
			buf.write_l(0x00600000) # Fixed vRes : Vertical resolution in pixels per inch
			buf.write_w(1) # int16 vResUnit : 1=display vertical resolution in pixels per inch; 2=display vertical resolution in pixels per cm
			buf.write_w(1) # int16 heightUnitDisplay : height as 1=inches; 2=cm; 3=points; 4=picas; 5=columns


		if write_version_info:
			# 4 : Signature: '8BIM'
			buf.write_string("8BIM")
			
			# 2 : # Unique identifier for the resource. 
			buf.write_w(0x421) #  Version Info. 4 bytes version, 1 byte hasRealMergedData , Unicode string: writer name, Unicode string: reader name, 4 bytes file version.
			
			# Variable : Name: Pascal string, padded to make the size even (a null name consists of two bytes of 0)
			buf.write_w(0)
			
			resource_length_pos = buf.index
			# 4 : # Actual size of resource data that follows
			buf.write_l(0)
			
			# Variable
			buf.write_l(1) # Version
			buf.write_b(1) # hasRealMergedData
			writeUTF16(buf, "Paint.NET PSD Plugin")
			writeUTF16(buf, "Paint.NET PSD Plugin 2.5.0")
			buf.write_l(1) # File version
			
			write_offset(buf, resource_length_pos)
			buf.align(2)
		
		write_offset(buf, image_resources_section_pos)
		
	
		# =================================================================
		# Layer and mask Information Section
		# =================================================================

		layer_and_mask_information_section_length_pos = buf.index
		# Length (4)
		buf.write_l(0)
		
		# Layer info Section(s ?)
		layer_info_offset = buf.index

		# 4 : Length of the layers info section, rounded up to a multiple of 2. (**PSB** length is 8 bytes.)
		buf.write_l(0)
		
		# 2 : Layer count. If it is a negative number, its absolute value is the number of layers and the first alpha channel contains the transparency data for the merged result.
		buf.write_w(len(self.layers))

		# Variable : Information about each layer. See Layer records describes the structure of this information for each layer.
		
		# Layer records
		for layer in self.layers:
			layer.write_to_buffer(buf)			
		
		

		# Channel image data. Contains one or more image data records
		for layer in self.layers:
			layer.write_channels_data_to_buffer(buf) 

		buf.write_w(0)
		write_offset(buf, layer_info_offset)
		# Variable
		
		buf.write_l(0)
		write_offset(buf, layer_and_mask_information_section_length_pos)

		buf.write_w(0)
		fusion_channels = self.get_fusioned_image()
		buf.write(fusion_channels.flatten())

	def get_fusioned_image(self, order="ARGB"):
		total_width, total_height = self.size

		# res: (total_height, total_width) uint32 RGBA
		res = np.zeros((total_height, total_width), dtype=np.uint32)

		alpha_bits = 0xFF << (8*order.index("A"))		
		for layer in self.layers:
			# print("processing layer: [%s]" % layer.name)
			if layer.is_visible:
				top, left, bottom, right = layer.get_bounding_box()
	
				# layer_data: shape=(h, w), uint32 ARGB
				layer_data = layer.get_data(order=order).copy()
				layer_data.dtype = np.uint32
	
				mask = (layer_data & alpha_bits) != 0
				res[top:bottom, left:right][mask] = layer_data[mask]
					
		res.dtype = np.uint8
		return res

	def save_fusioned_as_png(self, path):
		fusion = self.get_fusioned_image("RGBA")
		png.from_array(fusion, mode="RGBA").save(path)
		

# ===========================================================================
# Reader functions
# ===========================================================================

	
def _read_uncompressed_layer(buf, w, h):
	size = w*h
	res = np.array(buf.data[buf.index : buf.index + size], dtype = np.uint8)
	res.shape = (h, w)
	return res

def _read_compressed_layer(buf, w, h):
	buf.save_state()
	for _ in range(h):
		buf.read_w()
	size = w*h
	unc = np.zeros(size, dtype = np.uint8)
	i = 0
	
	while i < size:
		hdr = buf.read_b(signed = True)
		if hdr >= 0:
			n = hdr + 1
			unc[i : i + n] = buf.data[buf.index : buf.index + n]
			i += n
			buf.index += n
		elif hdr > -128:
			v = buf.read_b()
			n = 1 - hdr
			unc[i : i + n] = v
			i += n	
	unc.shape = (h, w)
	
	buf.restore_state()
	return unc

def load_psd(path):
	source = Buffer.load(path)

	assert source.read_string(n_chars = 4) == "8BPS"

	source.read_w()
	source.advance_index_by(6)

	pic_nb_channels = source.read_w()
	pic_height = source.read_l()
	pic_width = source.read_l()
	pic_depth = source.read_w()
	pic_color_mode = source.read_w()

#	print("nb_channels: %d" % pic_nb_channels)
#	print("width: %d" % pic_width)
#	print("height: %d" % pic_height)
#	print("depth: %d" % pic_depth)
#	print("color_mode: %d" % pic_color_mode)
	
#	color_mode_data_section = 0x1A
	length = source.read_l()
#	print("length of color mode data section: %d" % length)
	if length and length != 768:
		raise Exception("Unsupported color mode")
	if pic_color_mode == 2:
		pic_palette = np.zeros((256, 4), dtype=np.uint8)
		for x in range(256):
			pic_palette[x, 0] = 0xFF
			pic_palette[x, 1] = source.read_b()
			pic_palette[x, 2] = source.read_b()
			pic_palette[x, 3] = source.read_b()
		
#	source.advance_index_by(length)

	image_ressource_section = source.index
#	print("image ressource section starts at %X" % image_ressource_section)
	
	layer_info_section = image_ressource_section + source.read_l(image_ressource_section) + 4
#	print("layer info section starts at %X" % layer_info_section)
	
	source.set_index(layer_info_section + 8)
	nb_layers = source.read_w()

	layers = []
	
	for i in range(nb_layers):
		layer = {}
		layers += [layer]
		top = source.read_l()
		left = source.read_l()
		bottom = source.read_l()
		right = source.read_l()
		
#		print("bounding_box: top=%d left=%d bottom=%d right=%d" % (top, left, bottom, right))
		layer['rect'] = (top, left, bottom, right)
		
		nb_channels = source.read_w() # nb_channels
		channel_sizes = []
		for _ in range(nb_channels):
			source.read_w()
			channel_sizes += [source.read_l()]
		
		layer['channel_sizes'] = channel_sizes
	
		source.read_l() #8BIM
		source.read_string(n_chars = 4)
		source.read_l()
		delta = source.read_l()
		source.save_state()

#		 source.advance_index_by(delta)

		# Layer mask data
		layer_mask_data_size = source.read_l()
		source.advance_index_by(layer_mask_data_size)
		
		# Layer Blending Range
		layer_blending_range_size = source.read_l()
		source.advance_index_by(layer_blending_range_size)
		
		# Layer Name
		layer_name_size = source.read_b()
		source.advance_index_by(layer_name_size)
		
		source.align()
		if source.read_b(source.index) != 0x38:
			source.read_w()

		# unicode layer name
		source.read_l() #8BIM
		tag_ = source.read_string(n_chars = 4)
		# print tag_
		if tag_ == 'luni':
			source.read_l()
			sz = source.read_l()
			name = ''
			for _ in range(sz):
				c = source.read_w()
				name += chr(c)
			layer['name'] = name
		else:
			# print 'no name'
			layer['name'] = ''
		
		source.restore_state()
		source.advance_index_by(delta)
		
	result = []
	for i, layer in enumerate(layers):
		top, left, bottom, right = layer['rect']
#		print("Layer %d: top=%d, left=%d, bottom=%d, right=%d" % (i, top, left, bottom, right))
		w = right - left
		h = bottom - top
		
		channels = []
		if pic_color_mode == 2:
			# indexed colors
			raise Exception()
		
		elif pic_color_mode == 3:
			for j in range(4):
#				print("layer %d channel %d starts at %X" % (i, j, source.index))
				is_compressed = source.read_w()
				if is_compressed == 1:
#					print("compressed data")
					channels += [PsdChannel(j - 1, _read_compressed_layer(source, w, h))]
				elif is_compressed == 0:
#					print("uncompressed data")
					channels += [PsdChannel(j - 1, _read_uncompressed_layer(source, w, h))]
				else:
					raise Exception("bad compression flag at %X" % (source.index - 2))
	
				source.advance_index_by(layer['channel_sizes'][j] - 2)
	
		result += [
			PsdLayer(
				name = layer['name'],
				offset = (left, top),
				size = (w, h),
				channels = channels
			)
		]
				
	return PsdFile(
		(pic_width, pic_height), 
		result,
		color_mode = pic_color_mode)


if __name__ == '__main__':
	if True:
		# Test 1

		# load a psd file
		psd_file = load_psd('test/test1.psd')

		# extract all layers
		print("%d layers loaded" % psd_file.nb_layers)
		for layer in psd_file.layers:
			layer.save_as_png("test/test1-%s.png" % layer.name, crop=True)
		
	if True:
		# load a psd file
		psd_file = load_psd('test/test1.psd')
		psd_file.save("test/res1.psd")
	
	if True:
		# load a psd file
		psd_file = load_psd('test/test1.psd')
		
		psd_file.layers[2].hide()

		psd_file.save_fusioned_as_png("test/fusion.png")
		
	if True:
		# create psd by adding layers
		psd_file = PsdFile()
		
		# create layers
		image_1 = load_png("test/layer01.png")
		layer_1 = PsdLayer("Layer 1", (0, 0), image=image_1)
		psd_file.add_layer(layer_1)

		image_2 = load_png("test/layer02.png")
		layer_2 = PsdLayer("Layer 2", (4, 0), image=image_2)
		psd_file.add_layer(layer_2)
		
		image_3 = load_png("test/layer03.png")
		layer_3 = PsdLayer("Layer 3", (0, 4), image=image_3)
		psd_file.add_layer(layer_3)

		image_4 = load_png("test/layer04.png")
		layer_4 = PsdLayer("Layer 4", (4, 4), image=image_4)
		psd_file.add_layer(layer_4)

		psd_file.save("test/res2.psd")

	if True:
		# create psd by removing layers
		psd_file = load_psd("test/test1.psd")
		
		psd_file.remove_layer(psd_file.get_by_name("Calque 3"))

		psd_file.save("test/res3.psd")
	
	if True:
		# create quick psd file from png
		psd_file = PsdFile.from_images(["test/layer01.png", "test/layer02.png", "test/layer03.png"])
		psd_file.save("test/res4.psd")
